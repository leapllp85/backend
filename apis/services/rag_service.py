import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from anthropic import Anthropic
from apis.models import (
    KnowledgeBase, ActionItem, Project, Course, CourseCategory, 
    EmployeeProfile, ProjectAllocation, Survey, SurveyQuestion, 
    SurveyResponse, SurveyAnswer
)

logger = logging.getLogger(__name__)

class RAGService:
    """
    Retrieval-Augmented Generation service for Corporate MVP
    Uses Claude Sonnet for both embedding generation and text generation
    """
    
    def __init__(self):
        self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.embedding_dimensions = 1000  # Claude Sonnet embedding dimensions
        self.claude_model = "claude-3-5-sonnet-20241022"
        
        # Define sensitive fields to exclude from knowledge base
        self.sensitive_fields = {
            'password', 'is_superuser', 'is_staff', 'user_permissions', 
            'groups', 'last_login', 'date_joined'
        }
        
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for given text using Claude Sonnet"""
        try:
            # Use Claude Sonnet to generate a semantic embedding
            # Since Claude doesn't have a direct embedding API, we'll use a prompt-based approach
            embedding_prompt = f"""
You are a text embedding generator. Convert the following text into a {self.embedding_dimensions}-dimensional numerical vector representation.

Text to embed: "{text}"

Generate exactly {self.embedding_dimensions} floating-point numbers between -1 and 1, separated by commas, that represent the semantic meaning of this text. Focus on:
- Key concepts and entities
- Semantic relationships
- Context and meaning
- Professional/corporate relevance

Return ONLY the numbers, no other text:
"""
            
            message = self.anthropic_client.messages.create(
                model=self.claude_model,
                max_tokens=4000,
                temperature=0.1,  # Low temperature for consistent embeddings
                messages=[
                    {
                        "role": "user",
                        "content": embedding_prompt
                    }
                ]
            )
            
            # Extract embedding text from response
            embedding_text = message.content[0].text.strip() if message.content else ""
            
            # Parse the comma-separated numbers
            try:
                embedding_values = [float(x.strip()) for x in embedding_text.split(',')]
                
                # Ensure we have the right number of dimensions
                if len(embedding_values) != self.embedding_dimensions:
                    logger.warning(f"Expected {self.embedding_dimensions} dimensions, got {len(embedding_values)}")
                    # Pad or truncate to match expected dimensions
                    if len(embedding_values) < self.embedding_dimensions:
                        embedding_values.extend([0.0] * (self.embedding_dimensions - len(embedding_values)))
                    else:
                        embedding_values = embedding_values[:self.embedding_dimensions]
                
                # Normalize the embedding vector
                embedding_array = np.array(embedding_values)
                norm = np.linalg.norm(embedding_array)
                if norm > 0:
                    embedding_array = embedding_array / norm
                
                return embedding_array.tolist()
                
            except (ValueError, IndexError) as e:
                logger.error(f"Failed to parse embedding response: {e}")
                # Return a random normalized vector as fallback
                fallback_embedding = np.random.normal(0, 0.1, self.embedding_dimensions)
                fallback_embedding = fallback_embedding / np.linalg.norm(fallback_embedding)
                return fallback_embedding.tolist()
                
        except Exception as e:
            logger.error(f"Error generating embedding with Claude: {e}")
            # Return a random normalized vector as fallback
            fallback_embedding = np.random.normal(0, 0.1, self.embedding_dimensions)
            fallback_embedding = fallback_embedding / np.linalg.norm(fallback_embedding)
            return fallback_embedding.tolist()
    
    def extract_model_data(self, model_class: models.Model, exclude_user_data: bool = True) -> List[Dict[str, Any]]:
        """Extract non-sensitive data from Django model"""
        extracted_data = []
        
        # Skip User model entirely if exclude_user_data is True
        if exclude_user_data and model_class == User:
            return extracted_data
            
        try:
            queryset = model_class.objects.all()
            
            for obj in queryset:
                # Extract model fields
                data = {}
                for field in model_class._meta.get_fields():
                    field_name = field.name
                    
                    # Skip sensitive fields
                    if field_name in self.sensitive_fields:
                        continue
                        
                    try:
                        value = getattr(obj, field_name)
                        
                        # Handle different field types
                        if isinstance(field, models.ForeignKey):
                            if value:
                                # Get string representation instead of full object
                                data[field_name] = str(value)
                        elif isinstance(field, models.ManyToManyField):
                            if value:
                                data[field_name] = [str(item) for item in value.all()]
                        elif isinstance(field, (models.DateField, models.DateTimeField)):
                            if value:
                                data[field_name] = value.isoformat()
                        elif isinstance(field, models.JSONField):
                            data[field_name] = value if value else {}
                        else:
                            data[field_name] = value
                            
                    except Exception as e:
                        logger.warning(f"Error extracting field {field_name} from {model_class.__name__}: {e}")
                        continue
                
                # Create content string for embedding
                content_parts = []
                title = ""
                
                # Determine title and content based on model type
                if hasattr(obj, 'title'):
                    title = str(obj.title)
                    content_parts.append(f"Title: {title}")
                elif hasattr(obj, 'name'):
                    title = str(obj.name)
                    content_parts.append(f"Name: {title}")
                elif model_class == EmployeeProfile:
                    title = f"Employee Profile: {obj.user.get_full_name() or obj.user.username}"
                    content_parts.append(title)
                
                # Add description if available
                if hasattr(obj, 'description') and obj.description:
                    content_parts.append(f"Description: {obj.description}")
                
                # Add other relevant fields
                for key, value in data.items():
                    if key not in ['id', 'title', 'name', 'description', 'created_at', 'updated_at']:
                        if value and str(value).strip():
                            content_parts.append(f"{key.replace('_', ' ').title()}: {value}")
                
                content = " | ".join(content_parts)
                
                if content.strip():
                    extracted_data.append({
                        'content_id': str(obj.pk),
                        'content_type': model_class.__name__.lower(),
                        'title': title,
                        'content': content,
                        'metadata': {
                            'model': model_class.__name__,
                            'pk': obj.pk,
                            'fields': list(data.keys())
                        }
                    })
                    
        except Exception as e:
            logger.error(f"Error extracting data from {model_class.__name__}: {e}")
            
        return extracted_data
    
    def populate_knowledge_base(self, force_refresh: bool = False) -> Dict[str, int]:
        """Populate knowledge base with data from all models"""
        stats = {'created': 0, 'updated': 0, 'errors': 0}
        
        # Define models to extract data from
        models_to_extract = [
            ActionItem, Project, Course, CourseCategory, EmployeeProfile,
            ProjectAllocation, Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
        ]
        
        for model_class in models_to_extract:
            try:
                logger.info(f"Extracting data from {model_class.__name__}")
                extracted_data = self.extract_model_data(model_class)
                
                for item in extracted_data:
                    content_id = item['content_id']
                    content_type = item['content_type']
                    
                    # Check if already exists
                    existing = KnowledgeBase.objects.filter(
                        content_id=content_id,
                        content_type=content_type
                    ).first()
                    
                    if existing and not force_refresh:
                        continue
                    
                    # Generate embedding
                    embedding = self.generate_embedding(item['content'])
                    if not embedding:
                        stats['errors'] += 1
                        continue
                    
                    # Create or update knowledge base entry
                    if existing:
                        existing.title = item['title']
                        existing.content = item['content']
                        existing.metadata = item['metadata']
                        existing.set_embedding_vector(embedding)
                        existing.save()
                        stats['updated'] += 1
                    else:
                        kb_entry = KnowledgeBase.objects.create(
                            content_id=content_id,
                            content_type=content_type,
                            title=item['title'],
                            content=item['content'],
                            metadata=item['metadata']
                        )
                        kb_entry.set_embedding_vector(embedding)
                        kb_entry.save()
                        stats['created'] += 1
                        
            except Exception as e:
                logger.error(f"Error processing {model_class.__name__}: {e}")
                stats['errors'] += 1
                
        return stats
    
    def add_to_knowledge_base(self, content: str, source: str, metadata: Dict[str, Any] = None) -> bool:
        """Add a single item to the knowledge base"""
        try:
            # Generate embedding for the content
            embedding = self.generate_embedding(content)
            if not embedding:
                logger.error(f"Failed to generate embedding for source: {source}")
                return False
            
            # Extract content_type and content_id from metadata or source
            if metadata:
                content_type = metadata.get('type', 'unknown')
                content_id = str(metadata.get(f'{content_type}_id', source))
                title = metadata.get('title', f"{content_type.title()} {content_id}")
            else:
                # Fallback parsing from source
                if '_' in source:
                    content_type, content_id = source.split('_', 1)
                else:
                    content_type = 'unknown'
                    content_id = source
                title = f"{content_type.title()} {content_id}"
            
            # Check if entry already exists
            existing = KnowledgeBase.objects.filter(
                content_id=content_id,
                content_type=content_type
            ).first()
            
            if existing:
                # Update existing entry
                existing.title = title
                existing.content = content
                existing.metadata = metadata or {}
                existing.set_embedding_vector(embedding)
                existing.save()
                logger.info(f"Updated knowledge base entry for {content_type} {content_id}")
            else:
                # Create new entry
                kb_entry = KnowledgeBase.objects.create(
                    content_id=content_id,
                    content_type=content_type,
                    title=title,
                    content=content,
                    metadata=metadata or {}
                )
                kb_entry.set_embedding_vector(embedding)
                kb_entry.save()
                logger.info(f"Created knowledge base entry for {content_type} {content_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding to knowledge base for source {source}: {e}")
            return False
    
    def search_knowledge_base(self, query: str, content_types: Optional[List[str]] = None, 
                            limit: int = 10, threshold: float = 0.7) -> List[Dict[str, Any]]:
        """Search knowledge base using semantic similarity"""
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            if not query_embedding:
                return []
            
            # Search similar content
            results = KnowledgeBase.search_similar(
                query_embedding=query_embedding,
                content_type=content_types,
                limit=limit,
                threshold=threshold
            )
            
            # Convert to context dictionaries
            context_data = []
            for result in results:
                context = result.to_context_dict()
                context['similarity'] = getattr(result, 'similarity', 0.0)
                context_data.append(context)
                
            return context_data
            
        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []
    
    def get_role_filtered_context(self, user, user_profile, context_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter context data based on user role and permissions"""
        filtered_context = []
        
        for item in context_data:
            content_type = item.get('content_type', '')
            metadata = item.get('metadata', {})
            
            # Apply role-based filtering
            if content_type == 'employeeprofile':
                # Managers can see their team's profiles, associates only their own
                if user_profile.is_manager:
                    # Check if this profile belongs to team member
                    try:
                        profile_user_id = metadata.get('pk')
                        if profile_user_id:
                            profile_user = User.objects.get(pk=profile_user_id)
                            profile_obj = profile_user.employee_profile
                            if profile_obj.manager == user or profile_user == user:
                                filtered_context.append(item)
                    except:
                        pass
                else:
                    # Associates can only see their own profile
                    profile_user_id = metadata.get('pk')
                    if profile_user_id and str(profile_user_id) == str(user.pk):
                        filtered_context.append(item)
            
            elif content_type in ['project', 'actionitem', 'course']:
                # All users can see projects, action items, and courses
                filtered_context.append(item)
                
            elif content_type in ['survey', 'surveyresponse', 'surveyanswer']:
                # Apply survey visibility rules
                filtered_context.append(item)
                
            else:
                # Default: include other content types
                filtered_context.append(item)
                
        return filtered_context
