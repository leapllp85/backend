from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from apis.permissions import IsManager
from apis.models import EmployeeProfile, Project, Course, Survey, ActionItem, ProjectAllocation, Conversation, ConversationMessage
from anthropic import Anthropic
from django.conf import settings
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
import json
import logging
import hashlib
import time

logger = logging.getLogger(__name__)

class ChatAPIView(APIView):
    """RAG-powered chat API with Anthropic Claude for data analysis and component generation"""
    permission_classes = [IsAuthenticated, IsManager]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        
        # Cache configuration
        self.cache_ttl = getattr(settings, 'CHAT_RESPONSE_TTL', 21600)  # 6 hours default (was 1 hour)
        self.cache_prefix = 'llm_chat'
        self.context_cache_ttl = getattr(settings, 'CHAT_CONTEXT_TTL', 21600)  # 6 hours for context data (was 30 minutes)
        self.query_similarity_threshold = 0.85  # Threshold for similar queries

    def post(self, request, *args, **kwargs):
        try:
            # Accept both 'query' and 'prompt' parameters for compatibility
            user_query = request.data.get('query', '').strip() or request.data.get('prompt', '').strip()
            conversation_id = request.data.get('conversation_id')
            
            if not user_query:
                return JsonResponse({
                    "error": "Query is required",
                    "success": False
                }, status=400)

            # Get user profile
            user_profile = request.user.employee_profile

            # Check cache for similar queries first
            cached_response = self.get_cached_response(request.user.username, user_query, user_profile)
            if cached_response:
                logger.info(f"Cache hit for user {request.user.username}, query: {user_query[:50]}...")
                
                # Still create conversation and messages for tracking
                conversation = self.get_or_create_conversation(request.user, conversation_id, user_query)
                user_message = ConversationMessage.objects.create(
                    conversation=conversation,
                    role='user',
                    content=user_query
                )
                assistant_message = ConversationMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=f"Generated analysis for: {user_query} (cached)",
                    analysis_data=cached_response.get('analysis'),
                    queries_data=cached_response.get('queries'),
                    dataset=cached_response.get('dataset')
                )
                
                # Add conversation metadata to cached response
                cached_response.update({
                    "conversation_id": str(conversation.id),
                    "message_id": str(assistant_message.id),
                    "cached": True
                })
                
                return JsonResponse(cached_response)

            # Handle conversation management
            conversation = self.get_or_create_conversation(request.user, conversation_id, user_query)
            
            # Save user message
            user_message = ConversationMessage.objects.create(
                conversation=conversation,
                role='user',
                content=user_query
            )

            # Get context data (with caching)
            context_data = self.get_cached_database_context(request.user, user_profile, user_query)

            if not context_data:
                error_message = "No relevant information found for your query. Try rephrasing or asking about projects, employees, courses, or surveys."
                
                # Save error as assistant message
                ConversationMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=error_message
                )
                
                return JsonResponse({
                    "error": error_message,
                    "success": False,
                    "conversation_id": str(conversation.id)
                }, status=404)

            # Generate structured data response using Claude
            response_data = self.generate_claude_data_response(
                user_query=user_query,
                context_data=context_data,
                user_profile=user_profile
            )

            # Save assistant response
            assistant_message = ConversationMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=f"Generated analysis for: {user_query}",
                analysis_data=response_data.get('analysis'),
                queries_data=response_data.get('queries'),
                dataset=response_data.get('dataset')
            )

            # Optimize response - only return essential data for frontend
            # Map dataset to components by component IDs (only includes components with data)
            dataset_by_component = self.map_dataset_to_components(response_data.get('components', []), response_data.get('dataset', []))
            
            # Filter components to only include those with data
            valid_components = []
            for component in response_data.get('components', []):
                component_id = component.get('id', f'component_{len(valid_components) + 1}')
                if component_id in dataset_by_component:
                    valid_components.append(component)
            
            optimized_response = {
                "success": True,
                "conversation_id": str(conversation.id),
                "message_id": str(assistant_message.id),
                "layout": response_data.get('layout', {}),
                "components": valid_components,
                "dataset": dataset_by_component,
                "insights": response_data.get('insights', {}),
                "cached": False
            }
            
            # Cache the successful response (only if it contains meaningful data)
            self.cache_response(request.user.username, user_query, optimized_response, user_profile)
            
            return JsonResponse(optimized_response)

        except Exception as e:
            logger.error(f"Error in ChatAPIView: {e}")
            return JsonResponse({
                "error": f"An error occurred while processing your request: {str(e)}",
                "success": False
            }, status=500)

    def get_cache_key(self, username: str, query: str, user_role: str = None) -> str:
        """Generate a consistent cache key for user queries"""
        # Normalize query for better cache hits
        normalized_query = self.normalize_query(query)
        
        # Create hash of normalized query to handle long queries
        query_hash = hashlib.md5(normalized_query.encode('utf-8')).hexdigest()
        
        # Include user role for permission-based caching
        role_suffix = f"_{user_role}" if user_role else ""
        
        return f"{self.cache_prefix}:{username}:{query_hash}{role_suffix}"
    
    def normalize_query(self, query: str) -> str:
        """Normalize query for better cache matching"""
        # Convert to lowercase and strip whitespace
        normalized = query.lower().strip()
        
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        
        # Remove common variations that don't change meaning
        replacements = {
            'show me': 'show',
            'can you': '',
            'please': '',
            'could you': '',
            'i want to': '',
            'i need to': '',
            'help me': '',
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        # Remove extra spaces again after replacements
        normalized = ' '.join(normalized.split())
        
        return normalized
    
    def calculate_query_similarity(self, query1: str, query2: str) -> float:
        """Calculate similarity between two queries using simple word overlap"""
        words1 = set(self.normalize_query(query1).split())
        words2 = set(self.normalize_query(query2).split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
    
    def get_cached_response(self, username: str, query: str, user_profile) -> dict:
        """Get cached response for user query with similarity matching"""
        user_role = 'manager' if user_profile.is_manager else 'associate'
        
        # Try exact match first
        cache_key = self.get_cache_key(username, query, user_role)
        cached_data = cache.get(cache_key)
        
        if cached_data:
            logger.info(f"Exact cache hit for key: {cache_key}")
            return cached_data
        
        # Try similarity matching for recent queries
        user_queries_key = f"{self.cache_prefix}:queries:{username}"
        recent_queries = cache.get(user_queries_key, [])
        
        for recent_query_data in recent_queries:
            similarity = self.calculate_query_similarity(query, recent_query_data['query'])
            
            if similarity >= self.query_similarity_threshold:
                similar_cache_key = self.get_cache_key(username, recent_query_data['query'], user_role)
                similar_cached_data = cache.get(similar_cache_key)
                
                if similar_cached_data:
                    logger.info(f"Similar query cache hit (similarity: {similarity:.2f}): {recent_query_data['query'][:50]}...")
                    return similar_cached_data
        
        return None
    
    def cache_response(self, username: str, query: str, response_data: dict, user_profile):
        """Cache the response data for future use only if it contains meaningful data"""
        # Check if response contains meaningful data before caching
        if not self._should_cache_response(response_data):
            logger.info(f"Skipping cache for user {username} - empty or invalid dataset")
            return
        
        user_role = 'manager' if user_profile.is_manager else 'associate'
        
        # Cache the response
        cache_key = self.get_cache_key(username, query, user_role)
        
        # Prepare data for caching (remove conversation-specific fields)
        cacheable_data = response_data.copy()
        cacheable_data.pop('conversation_id', None)
        cacheable_data.pop('message_id', None)
        cacheable_data.pop('cached', None)
        
        cache.set(cache_key, cacheable_data, self.cache_ttl)
        
        # Update recent queries list for similarity matching
        user_queries_key = f"{self.cache_prefix}:queries:{username}"
        recent_queries = cache.get(user_queries_key, [])
        
        # Add new query to the beginning of the list
        query_data = {
            'query': query,
            'timestamp': time.time(),
            'cache_key': cache_key
        }
        
        # Keep only recent queries (last 20)
        recent_queries = [query_data] + [q for q in recent_queries if q['query'] != query][:19]
        
        cache.set(user_queries_key, recent_queries, self.cache_ttl)
        
        logger.info(f"Cached response for key: {cache_key}")
    
    def _should_cache_response(self, response_data: dict) -> bool:
        """Determine if response should be cached based on data quality"""
        # Don't cache if response is not successful
        if not response_data.get('success', True):
            return False
        
        # Check dataset validity
        dataset = response_data.get('dataset', {})
        
        # If dataset is empty or not a dict, don't cache
        if not dataset or not isinstance(dataset, dict):
            return False
        
        # Check if any component has meaningful data
        has_meaningful_data = False
        
        for component_id, component_data in dataset.items():
            if not isinstance(component_data, dict):
                continue
                
            data = component_data.get('data', [])
            row_count = component_data.get('row_count', 0)
            
            # Consider data meaningful if:
            # 1. Has actual data rows
            # 2. Row count > 0
            # 3. Data is not empty list
            if data and isinstance(data, list) and len(data) > 0 and row_count > 0:
                has_meaningful_data = True
                break
        
        # Also check components for meaningful content
        components = response_data.get('components', [])
        if not has_meaningful_data and components:
            # If we have components but no dataset, still might be worth caching
            # (e.g., insights-only responses)
            insights = response_data.get('insights', {})
            if insights and any(insights.get(key) for key in ['key_findings', 'recommendations', 'next_steps']):
                has_meaningful_data = True
        
        return has_meaningful_data
    
    def get_cached_database_context(self, user, user_profile, user_query):
        """Get database context with caching support"""
        # Create cache key for context data
        context_cache_key = f"{self.cache_prefix}:context:{user.username}:{user_profile.is_manager}"
        
        # Try to get from cache first
        cached_context = cache.get(context_cache_key)
        if cached_context:
            logger.info(f"Context cache hit for user: {user.username}")
            return cached_context
        
        # Get fresh context data
        context_data = self.get_database_context(user, user_profile, user_query)
        
        # Cache the context data for shorter duration
        if context_data:
            cache.set(context_cache_key, context_data, self.context_cache_ttl)
            logger.info(f"Cached context data for user: {user.username}")
        
        return context_data
    
    def invalidate_user_cache(self, username: str):
        """Invalidate all cached data for a specific user"""
        # Get user's recent queries to find cache keys
        user_queries_key = f"{self.cache_prefix}:queries:{username}"
        recent_queries = cache.get(user_queries_key, [])
        
        # Delete all cached responses for this user
        for query_data in recent_queries:
            cache.delete(query_data['cache_key'])
        
        # Delete the queries list
        cache.delete(user_queries_key)
        
        # Delete context cache for both manager and associate roles
        cache.delete(f"{self.cache_prefix}:context:{username}:True")
        cache.delete(f"{self.cache_prefix}:context:{username}:False")
        
        logger.info(f"Invalidated all cache for user: {username}")
    
    def invalidate_user_context_cache(self, username: str):
        """Invalidate only context cache for a specific user"""
        # Delete context cache for both manager and associate roles
        context_keys_deleted = 0
        
        manager_key = f"{self.cache_prefix}:context:{username}:True"
        associate_key = f"{self.cache_prefix}:context:{username}:False"
        
        if cache.get(manager_key):
            cache.delete(manager_key)
            context_keys_deleted += 1
            
        if cache.get(associate_key):
            cache.delete(associate_key)
            context_keys_deleted += 1
        
        if context_keys_deleted > 0:
            logger.info(f"Invalidated {context_keys_deleted} context cache entries for user: {username}")
    
    def invalidate_user_response_cache(self, username: str):
        """Invalidate only response caches for a specific user"""
        # Get user's recent queries to find cache keys
        user_queries_key = f"{self.cache_prefix}:queries:{username}"
        recent_queries = cache.get(user_queries_key, [])
        
        response_keys_deleted = 0
        
        # Delete all cached responses for this user
        for query_data in recent_queries:
            if cache.get(query_data['cache_key']):
                cache.delete(query_data['cache_key'])
                response_keys_deleted += 1
        
        # Clear the queries list since responses are invalidated
        if recent_queries:
            cache.delete(user_queries_key)
        
        if response_keys_deleted > 0:
            logger.info(f"Invalidated {response_keys_deleted} response cache entries for user: {username}")
    
    def get_cache_stats(self, username: str) -> dict:
        """Get detailed cache statistics for a user"""
        user_queries_key = f"{self.cache_prefix}:queries:{username}"
        recent_queries = cache.get(user_queries_key, [])
        
        # Check context cache status
        manager_context_cached = bool(cache.get(f"{self.cache_prefix}:context:{username}:True"))
        associate_context_cached = bool(cache.get(f"{self.cache_prefix}:context:{username}:False"))
        
        # Count active response caches
        active_response_caches = 0
        for query_data in recent_queries:
            if cache.get(query_data['cache_key']):
                active_response_caches += 1
        
        stats = {
            'cached_queries_count': len(recent_queries),
            'active_response_caches': active_response_caches,
            'context_cache_status': {
                'manager_context_cached': manager_context_cached,
                'associate_context_cached': associate_context_cached,
                'any_context_cached': manager_context_cached or associate_context_cached
            },
            'recent_queries': [{
                'query': q['query'][:50] + '...' if len(q['query']) > 50 else q['query'],
                'timestamp': q['timestamp'],
                'age_minutes': (time.time() - q['timestamp']) / 60,
                'cache_active': bool(cache.get(q['cache_key']))
            } for q in recent_queries[:5]],  # Show last 5
            'cache_efficiency': {
                'hit_rate_estimate': f"{(active_response_caches / len(recent_queries) * 100):.1f}%" if recent_queries else "0%",
                'total_queries_tracked': len(recent_queries)
            }
        }
        
        return stats

    def get_database_context(self, user, user_profile, user_query):
        """Get comprehensive context data from all database tables based on query"""
        context_data = []
        query_lower = user_query.lower()
        
        # Employee/wellness/performance queries
        if any(keyword in query_lower for keyword in [
            'mental health', 'wellness', 'risk', 'trigger', 'motivation', 
            'career opportunities', 'personal reason', 'team health',
            'employee', 'staff', 'wellbeing', 'mental state', 'performer', 
            'performance', 'top', 'best', 'team member', 'team', 'people',
            'worker', 'colleague', 'individual', 'person', 'human resources',
            'hr', 'talent', 'workforce', 'personnel', 'member', 'who',
            'profile', 'assessment', 'evaluation', 'rating', 'score'
        ]):
            context_data.extend(self.get_employee_context(user, user_profile))
        
        # Project/work/allocation queries
        if any(keyword in query_lower for keyword in [
            'project', 'allocation', 'assignment', 'work', 'task', 'job',
            'workload', 'capacity', 'utilization', 'resource', 'planning',
            'schedule', 'timeline', 'deadline', 'milestone', 'deliverable',
            'initiative', 'effort', 'activity', 'responsibility', 'duty',
            'portfolio', 'program', 'engagement', 'client', 'customer'
        ]):
            context_data.extend(self.get_project_context(user, user_profile))
        
        # Course/training/learning queries
        if any(keyword in query_lower for keyword in [
            'course', 'training', 'learning', 'skill', 'education', 'development',
            'certification', 'qualification', 'competency', 'knowledge',
            'curriculum', 'program', 'workshop', 'seminar', 'class',
            'lesson', 'module', 'study', 'teach', 'learn', 'upskill',
            'reskill', 'professional development', 'career development'
        ]):
            context_data.extend(self.get_course_context(user, user_profile))
        
        # Survey/feedback/response queries
        if any(keyword in query_lower for keyword in [
            'survey', 'feedback', 'response', 'questionnaire', 'poll',
            'form', 'input', 'opinion', 'rating', 'review', 'evaluation',
            'assessment', 'measurement', 'metric', 'satisfaction',
            'engagement', 'pulse', 'check-in', 'sentiment', 'voice'
        ]):
            context_data.extend(self.get_survey_context(user, user_profile))
        
        # Action item/task/todo queries
        if any(keyword in query_lower for keyword in [
            'action', 'item', 'todo', 'task', 'follow up', 'followup',
            'next step', 'recommendation', 'suggestion', 'improvement',
            'plan', 'goal', 'objective', 'target', 'outcome', 'result',
            'deliverable', 'commitment', 'agreement', 'decision'
        ]):
            context_data.extend(self.get_action_item_context(user, user_profile))
        
        # Analytics/reporting/dashboard queries
        if any(keyword in query_lower for keyword in [
            'report', 'dashboard', 'analytics', 'data', 'chart', 'graph',
            'metric', 'kpi', 'statistic', 'trend', 'analysis', 'insight',
            'summary', 'overview', 'breakdown', 'distribution', 'comparison',
            'benchmark', 'performance indicator', 'measurement'
        ]):
            # Get all context for comprehensive reporting
            context_data.extend(self.get_employee_context(user, user_profile))
            context_data.extend(self.get_project_context(user, user_profile))
            context_data.extend(self.get_course_context(user, user_profile))
            context_data.extend(self.get_survey_context(user, user_profile))
            context_data.extend(self.get_action_item_context(user, user_profile))
        
        # Time-based queries
        if any(keyword in query_lower for keyword in [
            'recent', 'latest', 'current', 'today', 'yesterday', 'week',
            'month', 'quarter', 'year', 'last', 'past', 'previous',
            'upcoming', 'future', 'schedule', 'timeline', 'when', 'time'
        ]):
            # Get all context for time-based analysis
            context_data.extend(self.get_employee_context(user, user_profile))
            context_data.extend(self.get_project_context(user, user_profile))
            context_data.extend(self.get_course_context(user, user_profile))
            context_data.extend(self.get_survey_context(user, user_profile))
            context_data.extend(self.get_action_item_context(user, user_profile))
        
        # Comparison/ranking queries
        if any(keyword in query_lower for keyword in [
            'compare', 'comparison', 'versus', 'vs', 'against', 'between',
            'rank', 'ranking', 'order', 'sort', 'top', 'bottom', 'best',
            'worst', 'highest', 'lowest', 'most', 'least', 'first', 'last'
        ]):
            # Get all context for comparative analysis
            context_data.extend(self.get_employee_context(user, user_profile))
            context_data.extend(self.get_project_context(user, user_profile))
            context_data.extend(self.get_course_context(user, user_profile))
            context_data.extend(self.get_survey_context(user, user_profile))
        
        # General/broad queries - always include comprehensive context
        if any(keyword in query_lower for keyword in [
            'show', 'display', 'list', 'all', 'everything', 'overview',
            'summary', 'what', 'how', 'why', 'where', 'which', 'status',
            'update', 'information', 'details', 'help', 'assist'
        ]) or not context_data:
            # Ensure comprehensive context for broad or unmatched queries
            context_data.extend(self._get_fallback_context(user, user_profile))
        
        # Final fallback - if still no context, force comprehensive retrieval
        if not context_data:
            logger.warning(f"No context found for query: {user_query}. Using emergency fallback.")
            context_data = self._get_emergency_fallback_context(user, user_profile)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_context = []
        for item in context_data:
            item_key = (item.get('content_id'), item.get('content_type'))
            if item_key not in seen:
                seen.add(item_key)
                unique_context.append(item)
        
        return unique_context
    
    def _get_fallback_context(self, user, user_profile):
        """Get comprehensive context with error handling"""
        fallback_context = []
        
        # Try each context type with individual error handling
        context_methods = [
            ('employee', self.get_employee_context),
            ('project', self.get_project_context),
            ('course', self.get_course_context),
            ('survey', self.get_survey_context),
            ('action_item', self.get_action_item_context)
        ]
        
        for context_type, method in context_methods:
            try:
                context_data = method(user, user_profile)
                if context_data:
                    fallback_context.extend(context_data)
                    logger.info(f"Successfully retrieved {len(context_data)} {context_type} context items")
                else:
                    logger.warning(f"No {context_type} context data available")
            except Exception as e:
                logger.error(f"Error retrieving {context_type} context: {e}")
                # Continue with other context types
                continue
        
        return fallback_context
    
    def _get_emergency_fallback_context(self, user, user_profile):
        """Emergency fallback when all else fails"""
        emergency_context = []
        
        try:
            # Try to get at least basic user information
            emergency_context.append({
                'content_id': str(user.id),
                'content_type': 'user_basic',
                'title': f"User: {user.get_full_name() or user.username}",
                'content': f"Current user: {user.get_full_name() or user.username} | "
                         f"Is Manager: {user_profile.is_manager if user_profile else False}",
                'metadata': {
                    'model': 'User',
                    'pk': user.id,
                    'username': user.username,
                    'is_manager': user_profile.is_manager if user_profile else False
                }
            })
            
            # Try to get basic system information
            emergency_context.append({
                'content_id': 'system_info',
                'content_type': 'system',
                'title': 'System Information',
                'content': 'Corporate MVP System - Employee wellness and performance management platform',
                'metadata': {
                    'model': 'System',
                    'available_features': ['employee_profiles', 'projects', 'courses', 'surveys', 'action_items']
                }
            })
            
            logger.info(f"Emergency fallback provided {len(emergency_context)} basic context items")
            
        except Exception as e:
            logger.error(f"Emergency fallback failed: {e}")
            # Absolute last resort - minimal context
            emergency_context = [{
                'content_id': 'minimal',
                'content_type': 'minimal',
                'title': 'Minimal Context',
                'content': 'System available for employee wellness and performance queries',
                'metadata': {'model': 'Minimal'}
            }]
        
        return emergency_context

    def get_employee_context(self, user, user_profile):
        """Get employee data directly from database with fallback handling"""
        context_data = []
        
        try:
            if not user_profile:
                logger.warning("No user profile available for employee context")
                return context_data
            if user_profile.is_manager:
                # Get team members' data
                team_members = EmployeeProfile.objects.filter(manager=user).select_related('user')
                
                for member in team_members:
                    context_data.append({
                        'content_id': str(member.id),
                        'content_type': 'employeeprofile',
                        'title': f"Employee: {member.user.get_full_name() or member.user.username}",
                        'content': f"Employee: {member.user.get_full_name() or member.user.username} | "
                                 f"Mental Health Risk: {member.mental_health} | "
                                 f"Motivation Factor Risk: {member.motivation_factor} | "
                                 f"Career Opportunities Risk: {member.career_opportunities} | "
                                 f"Personal Reason Risk: {member.personal_reason} | "
                                 f"Primary Trigger: {member.get_primary_trigger_display()} | "
                                 f"Suggested Risk Level: {member.suggested_risk} | "
                                 f"Manager Assessment Risk: {member.manager_assessment_risk}",
                        'metadata': {
                            'model': 'EmployeeProfile',
                            'pk': member.id,
                            'user_id': member.user.id,
                            'mental_health': member.mental_health,
                            'motivation_factor': member.motivation_factor,
                            'career_opportunities': member.career_opportunities,
                            'personal_reason': member.personal_reason,
                            'primary_trigger': member.primary_trigger,
                            'suggested_risk': member.suggested_risk,
                            'manager_assessment_risk': member.manager_assessment_risk
                        }
                    })
            else:
                # Get own data
                context_data.append({
                    'content_id': str(user_profile.id),
                    'content_type': 'employeeprofile',
                    'title': f"My Profile: {user.get_full_name() or user.username}",
                    'content': f"Employee: {user.get_full_name() or user.username} | "
                             f"Mental Health Risk: {user_profile.mental_health} | "
                             f"Motivation Factor Risk: {user_profile.motivation_factor} | "
                             f"Career Opportunities Risk: {user_profile.career_opportunities} | "
                             f"Personal Reason Risk: {user_profile.personal_reason} | "
                             f"Primary Trigger: {user_profile.get_primary_trigger_display()} | "
                             f"Suggested Risk Level: {user_profile.suggested_risk}",
                    'metadata': {
                        'model': 'EmployeeProfile',
                        'pk': user_profile.id,
                        'user_id': user.id,
                        'mental_health': user_profile.mental_health,
                        'motivation_factor': user_profile.motivation_factor,
                        'career_opportunities': user_profile.career_opportunities,
                        'personal_reason': user_profile.personal_reason,
                        'primary_trigger': user_profile.primary_trigger,
                        'suggested_risk': user_profile.suggested_risk
                    }
                })
                
        except Exception as e:
            logger.error(f"Error getting employee context: {e}")
            # Fallback: try to get basic user info
            try:
                context_data.append({
                    'content_id': str(user.id),
                    'content_type': 'user_fallback',
                    'title': f"User: {user.get_full_name() or user.username}",
                    'content': f"Basic user information: {user.get_full_name() or user.username}",
                    'metadata': {
                        'model': 'User',
                        'pk': user.id,
                        'fallback': True
                    }
                })
            except Exception as fallback_error:
                logger.error(f"Employee context fallback failed: {fallback_error}")
        
        return context_data

    def get_project_context(self, user, user_profile):
        """Get project data directly from database"""
        context_data = []
        
        try:
            if user_profile.is_manager:
                # Get projects for team members
                team_member_ids = EmployeeProfile.objects.filter(manager=user).values_list('user_id', flat=True)
                projects = Project.objects.filter(
                    project_allocations__employee__in=team_member_ids
                ).distinct()
            else:
                # Get own projects
                projects = Project.objects.filter(
                    project_allocations__employee=user
                ).distinct()
            
            for project in projects:
                context_data.append({
                    'content_id': str(project.id),
                    'content_type': 'project',
                    'title': f"Project: {project.title}",
                    'content': f"Project: {project.title} | "
                             f"Description: {project.description or 'N/A'} | "
                             f"Status: {project.status} | "
                             f"Criticality: {project.criticality} | "
                             f"Start Date: {project.start_date} | "
                             f"Go Live Date: {project.go_live_date}",
                    'metadata': {
                        'model': 'Project',
                        'pk': project.id,
                        'name': project.title,
                        'status': project.status,
                        'criticality': project.criticality
                    }
                })
                
        except Exception as e:
            logger.error(f"Error getting project context: {e}")
            
        return context_data

    def get_course_context(self, user, user_profile):
        """Get course data directly from database"""
        context_data = []
        
        try:
            courses = Course.objects.all()
            
            for course in courses:
                context_data.append({
                    'content_id': str(course.id),
                    'content_type': 'course',
                    'title': f"Course: {course.title}",
                    'content': f"Course: {course.title} | "
                             f"Categories: {', '.join([cat.name for cat in course.category.all()]) if course.category.exists() else 'N/A'} | "
                             f"Description: {course.description or 'N/A'}",
                    'metadata': {
                        'model': 'Course',
                        'pk': course.id,
                        'title': course.title,
                        'categories': [cat.name for cat in course.category.all()]
                    }
                })
                
        except Exception as e:
            logger.error(f"Error getting course context: {e}")
            
        return context_data

    def get_survey_context(self, user, user_profile):
        """Get survey data directly from database"""
        context_data = []
        
        try:
            surveys = Survey.objects.all().prefetch_related('questions')
            
            for survey in surveys:
                context_data.append({
                    'content_id': str(survey.id),
                    'content_type': 'survey',
                    'title': f"Survey: {survey.title}",
                    'content': f"Survey: {survey.title} | "
                             f"Description: {survey.description or 'N/A'} | "
                             f"Questions: {survey.questions.count()} | "
                             f"Created: {survey.created_at.date()}",
                    'metadata': {
                        'model': 'Survey',
                        'pk': survey.id,
                        'title': survey.title,
                        'question_count': survey.questions.count()
                    }
                })
                
        except Exception as e:
            logger.error(f"Error getting survey context: {e}")
            
        return context_data

    def get_action_item_context(self, user, user_profile):
        """Get action item data directly from database"""
        context_data = []
        
        try:
            if user_profile.is_manager:
                # Get action items for team
                team_member_ids = EmployeeProfile.objects.filter(manager=user).values_list('user_id', flat=True)
                action_items = ActionItem.objects.filter(
                    assigned_to__in=team_member_ids
                )
            else:
                # Get own action items
                action_items = ActionItem.objects.filter(
                    assigned_to=user
                )
            
            for item in action_items:
                context_data.append({
                    'content_id': str(item.id),
                    'content_type': 'actionitem',
                    'title': f"Action Item: {item.title}",
                    'content': f"Action Item: {item.title} | "
                             f"Status: {item.status} | "
                             f"Assigned to: {item.assigned_to.get_full_name() or item.assigned_to.username} | "
                             f"Action URL: {item.action}",
                    'metadata': {
                        'model': 'ActionItem',
                        'pk': item.id,
                        'title': item.title,
                        'status': item.status,
                        'assigned_to': item.assigned_to.username
                    }
                })
                
        except Exception as e:
            logger.error(f"Error getting action item context: {e}")
            
        return context_data

    def get_or_create_conversation(self, user, conversation_id, user_query):
        """Get existing conversation or create a new one"""
        if conversation_id:
            try:
                # Try to get existing conversation
                conversation = Conversation.objects.get(id=conversation_id, user=user)
                return conversation
            except Conversation.DoesNotExist:
                logger.warning(f"Conversation {conversation_id} not found for user {user.id}")
        
        # Create new conversation
        # Generate title from first few words of query
        title_words = user_query.split()[:5]
        title = ' '.join(title_words)
        if len(user_query.split()) > 5:
            title += '...'
        
        conversation = Conversation.objects.create(
            user=user,
            title=title[:255]  # Ensure title fits in field
        )
        
        return conversation

    def get_employee_wellness_context(self, user, user_profile):
        """Get employee wellness data directly from database for mental health queries"""
        context_data = []
        
        try:
            if user_profile.is_manager:
                # Get team members' wellness data
                team_members = EmployeeProfile.objects.filter(manager=user).select_related('user')
                
                for member in team_members:
                    wellness_data = {
                        'content_id': str(member.id),
                        'content_type': 'employeeprofile',
                        'title': f"Employee Wellness: {member.user.get_full_name() or member.user.username}",
                        'content': f"Employee: {member.user.get_full_name() or member.user.username} | "
                                 f"Mental Health Risk: {member.mental_health} | "
                                 f"Motivation Factor Risk: {member.motivation_factor} | "
                                 f"Career Opportunities Risk: {member.career_opportunities} | "
                                 f"Personal Reason Risk: {member.personal_reason} | "
                                 f"Primary Trigger: {member.get_primary_trigger_display()} | "
                                 f"Suggested Risk Level: {member.suggested_risk} | "
                                 f"Manager Assessment Risk: {member.manager_assessment_risk}",
                        'metadata': {
                            'model': 'EmployeeProfile',
                            'pk': member.id,
                            'user_id': member.user.id,
                            'mental_health': member.mental_health,
                            'motivation_factor': member.motivation_factor,
                            'career_opportunities': member.career_opportunities,
                            'personal_reason': member.personal_reason,
                            'primary_trigger': member.primary_trigger,
                            'suggested_risk': member.suggested_risk,
                            'manager_assessment_risk': member.manager_assessment_risk
                        }
                    }
                    context_data.append(wellness_data)
            else:
                # Get own wellness data
                wellness_data = {
                    'content_id': str(user_profile.id),
                    'content_type': 'employeeprofile',
                    'title': f"My Wellness Profile: {user.get_full_name() or user.username}",
                    'content': f"Employee: {user.get_full_name() or user.username} | "
                             f"Mental Health Risk: {user_profile.mental_health} | "
                             f"Motivation Factor Risk: {user_profile.motivation_factor} | "
                             f"Career Opportunities Risk: {user_profile.career_opportunities} | "
                             f"Personal Reason Risk: {user_profile.personal_reason} | "
                             f"Primary Trigger: {user_profile.get_primary_trigger_display()} | "
                             f"Suggested Risk Level: {user_profile.suggested_risk}",
                    'metadata': {
                        'model': 'EmployeeProfile',
                        'pk': user_profile.id,
                        'user_id': user.id,
                        'mental_health': user_profile.mental_health,
                        'motivation_factor': user_profile.motivation_factor,
                        'career_opportunities': user_profile.career_opportunities,
                        'personal_reason': user_profile.personal_reason,
                        'primary_trigger': user_profile.primary_trigger,
                        'suggested_risk': user_profile.suggested_risk
                    }
                }
                context_data.append(wellness_data)
                
        except Exception as e:
            logger.error(f"Error getting employee wellness context: {e}")
            
        return context_data

    def generate_claude_data_response(self, user_query: str, context_data: list, user_profile) -> dict:
        """Generate data analysis and component specification using Claude with RAG context"""
        
        # Prepare context summary for Claude
        context_summary = self.prepare_context_for_claude(context_data)
        
        # Get available models schema for query generation
        models_schema = self.get_models_schema()
        
        # Create comprehensive prompt for Claude with multicomponent support
        claude_prompt = f"""
You are an expert corporate data analyst and database query specialist with expertise in employee wellness and risk assessment. Analyze the user query and generate appropriate database queries along with multicomponent frontend specifications for dashboard-style rendering.

User Query: "{user_query}"
User Role: {'Manager' if user_profile.is_manager else 'Associate'}
User ID: {user_profile.user.id}

Available Database Models Schema:
{models_schema}

Relevant Corporate Data Context:
{context_summary}

IMPORTANT EMPLOYEE RISK ASSESSMENT GUIDELINES:
- For Manager users: Can query about their direct team members' risk assessments and mental health data
- For Associate users: Can only query about their own risk assessment data
- Mental Health queries should focus on: mental_health, motivation_factor, career_opportunities, personal_reason fields
- Risk levels are: 'High', 'Medium', 'Low'
- Primary triggers: MH=Mental Health, MT=Motivation Factor, CO=Career Opportunities, PR=Personal Reason
- Always respect privacy: Managers can only see data for employees where manager_id = {user_profile.user.id}

SAMPLE QUERIES FOR EMPLOYEE WELLNESS:
- "Show my team's mental health status" → Query apis_employeeprofile where manager_id = current_user
- "Who in my team has high mental health risk?" → Filter by mental_health = 'High' AND manager_id = current_user
- "Team motivation levels" → Show motivation_factor for team members
- "Employees with career opportunity concerns" → Filter by career_opportunities = 'High' risk
- "My team's primary triggers" → Show primary_trigger distribution for team

IMPORTANT: Always use actual Django table names and relationships in SQL queries:
- EmployeeProfile model → apis_employeeprofile table
- Project model → apis_project table  
- Course model → apis_course table
- Survey model → apis_survey table
- ActionItem model → apis_actionitem table
- ProjectAllocation model → apis_projectallocation table
- User model → auth_user table

CRITICAL: Course-User relationships:
- Course has ManyToMany with CourseCategory via apis_course_category table
- There is NO direct user-course relationship table
- Do NOT reference 'user_courses' table - it does not exist
- For course queries, use only apis_course and apis_coursecategory tables

EMPLOYEE-PROJECT RELATIONSHIPS:
- Use apis_projectallocation table to link users to projects
- Manager relationships: apis_employeeprofile.manager_id links to auth_user.id

FRONTEND COMPONENT TYPES AVAILABLE:
1. **Charts**: bar_chart, line_chart, pie_chart (uses DataVisualization component)
2. **Tables**: data_table, table (uses DataTable component with search, pagination, CSV export)
3. **Metrics**: metric_card, stat, card (uses MetricCard component with aggregation and trends)
4. **Lists**: list (uses ComponentRenderer list rendering)
5. **Insights**: insights_panel (uses InsightsPanel for key_findings, recommendations, next_steps)

COMPONENT DATA REQUIREMENTS:
- **Charts**: Require x_axis, y_axis properties and numerical data
- **Tables**: Require columns array and data array with search/filter capabilities
- **Metrics**: Require aggregation (sum|avg|max|min|count) and numerical field
- **Lists**: Display raw data as formatted list items
- **Insights**: Require insights object with key_findings, recommendations, next_steps arrays

Instructions:
1. Analyze the user query and determine what data is needed
2. Generate appropriate SQL queries respecting user role permissions
3. Design a multicomponent layout with multiple related visualizations
4. Specify component types, configurations, and layout arrangements
5. Include interactive features like filters, drill-downs, and actions
6. Provide comprehensive data transformation and formatting specs
7. Include insights and recommendations based on the context

IMPORTANT: Generate insights ONLY ONCE in the response:
- Include insights only in the main "insights" section at the end
- Do NOT create multiple insights_panel components
- Do NOT duplicate insights in component specifications
- If you need an insights component, reference the main insights section

Return your response as a JSON object with the following structure:
{{
    "success": true,
    "analysis": {{
        "query_intent": "Brief description of what the user is asking for",
        "data_requirements": ["list", "of", "required", "data", "points"],
        "visualization_strategy": "How multiple components work together",
        "primary_component": "main component type",
        "supporting_components": ["list", "of", "additional", "components"]
    }},
    "layout": {{
        "type": "dashboard|single|split|grid",
        "columns": 1,
        "rows": 1,
        "responsive": true,
        "spacing": "medium",
        "component_arrangement": [
            {{
                "component_id": "comp_1",
                "position": {{"row": 1, "col": 1, "span_col": 1, "span_row": 1}},
                "size": "large|medium|small"
            }}
        ]
    }},
    "components": [
        {{
            "id": "comp_1",
            "type": "bar_chart|line_chart|pie_chart|data_table|metric_card|list|insights_panel",
            "title": "Component title",
            "description": "Brief description (optional)",
            "properties": {{
                "x_axis": "field name for x-axis (charts only)",
                "y_axis": "field name for y-axis (charts/metrics)",
                "aggregation": "sum|avg|max|min|count (metrics only)",
                "filters": ["available", "filter", "options"]
            }}
        }}
    ],
    "queries": [
        {{
            "id": "query_1",
            "description": "What this query fetches",
            "sql": "Raw SQL query",
            "orm": "Django ORM equivalent",
            "expected_fields": ["field1", "field2", "field3"],
            "cache_duration": 300
        }}
    ],
    "data_processing": {{
        "transformations": ["list of data transformations needed"],
        "calculations": ["list of calculations to perform"],
        "formatting": ["list of formatting requirements"],
        "aggregations": ["list of aggregation operations"]
    }},
    "insights": {{
        "key_findings": ["insight1", "insight2"],
        "recommendations": ["recommendation1", "recommendation2"],
        "next_steps": ["action1", "action2"],
        "alerts": ["critical alerts or warnings"]
    }}
}}

Generate ONLY valid JSON. Do not include any markdown or explanations outside the JSON structure.
"""
        
        try:
            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0,
                messages=[
                    {
                        "role": "user",
                        "content": claude_prompt
                    }
                ]
            )
            
            # Extract and parse JSON content from response
            response_content = message.content[0].text.strip() if message.content else ""
            
            try:
                # Clean the response content before parsing
                cleaned_content = self._clean_json_response(response_content)
                
                # Parse the JSON response
                parsed_response = json.loads(cleaned_content)
                
                # Validate the response structure
                if not isinstance(parsed_response, dict):
                    raise ValueError("Response is not a dictionary")
                
                # Execute queries and optimize dataset
                if "queries" in parsed_response:
                    dataset = self.execute_queries(parsed_response["queries"])
                    parsed_response["dataset"] = self.optimize_dataset(dataset)
                    
                # Process multicomponent data if components are specified
                if "components" in parsed_response:
                    parsed_response = self.process_multicomponent_data(parsed_response)
                    
                # Remove unnecessary fields to reduce response size
                parsed_response = self.cleanup_response(parsed_response)
                
                return parsed_response
                
            except (json.JSONDecodeError, ValueError) as e:
                logger.error(f"Failed to parse Claude JSON response: {e}")
                logger.error(f"Raw response content: {response_content[:500]}...")
                
                # Try to extract JSON from markdown code blocks if present
                fallback_response = self._extract_json_from_markdown(response_content)
                if fallback_response:
                    return fallback_response
                
                return {
                    "success": False,
                    "error": "Failed to parse AI response - invalid JSON format",
                    "details": str(e),
                    "raw_response": response_content[:200] + "..." if len(response_content) > 200 else response_content
                }
                
        except Exception as e:
            logger.error(f"Claude API call error: {e}")
            return {
                "success": False,
                "error": f"Error generating response: {str(e)}"
            }
    
    def prepare_context_for_claude(self, context_data: list) -> str:
        """Prepare context data for Claude in a structured format"""
        if not context_data:
            return "No relevant data found."
            
        context_lines = []
        
        # Group context by content type
        grouped_context = {}
        for item in context_data:
            content_type = item.get('content_type', 'unknown')
            if content_type not in grouped_context:
                grouped_context[content_type] = []
            grouped_context[content_type].append(item)
        
        # Format each group
        for content_type, items in grouped_context.items():
            context_lines.append(f"\n{content_type.upper()} DATA:")
            for i, item in enumerate(items[:5], 1):  # Limit to top 5 per type
                title = item.get('title', 'No title')
                content = item.get('content', '')[:200] + '...' if len(item.get('content', '')) > 200 else item.get('content', '')
                similarity = item.get('similarity', 0.0)
                context_lines.append(f"{i}. {title} (Relevance: {similarity:.2f})")
                context_lines.append(f"   Content: {content}")
                
                # Add metadata if available
                metadata = item.get('metadata', {})
                if metadata:
                    context_lines.append(f"   Details: {json.dumps(metadata, default=str)}")
                context_lines.append("")
        
        return "\n".join(context_lines)

    def _clean_json_response(self, content: str) -> str:
        """Clean JSON response content to fix common formatting issues"""
        if not content:
            return content
        
        # Remove markdown code blocks if present
        if content.startswith('```json'):
            content = content[7:]  # Remove ```json
        if content.startswith('```'):
            content = content[3:]   # Remove ```
        if content.endswith('```'):
            content = content[:-3]  # Remove closing ```
        
        # Strip whitespace
        content = content.strip()
        
        # Only apply minimal cleaning - don't use aggressive regex that can corrupt valid JSON
        # Just try to parse as-is first, since Claude usually returns valid JSON
        return content
    
    def _extract_json_from_markdown(self, content: str) -> dict:
        """Try to extract JSON from markdown code blocks or find the largest JSON object"""
        import re
        
        # First, try to find JSON in code blocks
        json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
        matches = re.findall(json_pattern, content, re.DOTALL)
        
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue
        
        # Try to find the largest complete JSON object in the content
        # Look for opening brace and find matching closing brace
        start_idx = content.find('{')
        if start_idx == -1:
            return None
        
        brace_count = 0
        end_idx = start_idx
        
        for i in range(start_idx, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_idx = i
                    break
        
        if brace_count == 0:  # Found complete JSON object
            json_str = content[start_idx:end_idx + 1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError:
                pass
        
        return None

    def get_models_schema(self) -> str:
        """Get database models schema for query generation"""
        from apis.models import (
            EmployeeProfile, Project, Course, CourseCategory, 
            Survey, SurveyResponse, ActionItem
        )
        
        models = [
            (EmployeeProfile, "employees"),
            (Project, "projects"), 
            (Course, "courses"),
            (CourseCategory, "course_categories"),
            (Survey, "surveys"),
            (SurveyResponse, "survey_responses"),
            (ActionItem, "action_items")
        ]
        
        schema_lines = ["Available Database Models and Tables:\n"]
        
        for model, table_name in models:
            try:
                # Simple schema generation without external dependency
                fields = []
                actual_table_name = model._meta.db_table
                for field in model._meta.get_fields():
                    field_type = field.__class__.__name__
                    fields.append(f"- {field.name}: {field_type}")
                
                schema_lines.append(f"Table `{actual_table_name}` (alias: {table_name}, model: {model.__name__}) has the following fields:")
                schema_lines.extend(fields)
                schema_lines.append("")
            except Exception as e:
                logger.warning(f"Could not get schema for {model.__name__}: {e}")
                schema_lines.append(f"Table `{table_name}` (schema unavailable)")
                schema_lines.append("")
        
        # Add specific schema details for critical relationships
        schema_lines.append("IMPORTANT RELATIONSHIP DETAILS:")
        schema_lines.append("- EmployeeProfile.user_id links to auth_user.id (one-to-one)")
        schema_lines.append("- EmployeeProfile.manager_id links to auth_user.id (manager relationship)")
        schema_lines.append("- Project.assigned_to is ManyToMany with auth_user")
        schema_lines.append("- ProjectAllocation.employee_id links to auth_user.id (NOT user_id!)")
        schema_lines.append("- ProjectAllocation.project_id links to apis_project.id")
        schema_lines.append("- Course.category is ManyToMany with CourseCategory")
        schema_lines.append("")
        
        schema_lines.append("CRITICAL SQL FIELD NAMES:")
        schema_lines.append("- apis_projectallocation table uses 'employee_id' NOT 'user_id'")
        schema_lines.append("- apis_employeeprofile table uses 'user_id' and 'manager_id'")
        schema_lines.append("- Join ProjectAllocation: pa.employee_id = au.id")
        schema_lines.append("- Join EmployeeProfile: ep.user_id = au.id")
        schema_lines.append("")
        
        schema_lines.append("EMPLOYEE RISK ASSESSMENT FIELDS:")
        schema_lines.append("- Mental Health (mental_health): High/Medium/Low risk level")
        schema_lines.append("- Motivation Factor (motivation_factor): High/Medium/Low risk level")
        schema_lines.append("- Career Opportunities (career_opportunities): High/Medium/Low risk level")
        schema_lines.append("- Personal Reason (personal_reason): Personal circumstances risk level")
        schema_lines.append("- Manager Assessment (manager_assessment_risk): Manager's overall risk assessment")
        schema_lines.append("- Primary Trigger: MH=Mental Health, MT=Motivation, CO=Career Opportunities, PR=Personal Reason")
        schema_lines.append("- All Triggers: Comma-separated trigger codes")
        schema_lines.append("- Manager Relationship: manager_id field links to User who manages this employee")
        schema_lines.append("")
        
        return "\n".join(schema_lines)

    def execute_queries(self, queries: list) -> list:
        """Execute the generated queries and return results"""
        results = []
        
        for query_info in queries:
            try:
                sql_query = query_info.get("sql", "")
                description = query_info.get("description", "")
                expected_fields = query_info.get("expected_fields", [])
                
                if not sql_query:
                    results.append({
                        "description": description,
                        "error": "No SQL query provided",
                        "data": []
                    })
                    continue
                
                # Execute the SQL query
                with connection.cursor() as cursor:
                    cursor.execute(sql_query)
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchall()
                    
                    # Convert to list of dictionaries
                    data = []
                    for row in rows:
                        row_dict = dict(zip(columns, row))
                        # Convert any non-serializable objects to strings
                        for key, value in row_dict.items():
                            if hasattr(value, 'isoformat'):  # datetime objects
                                row_dict[key] = value.isoformat()
                            elif not isinstance(value, (str, int, float, bool, type(None))):
                                row_dict[key] = str(value)
                        data.append(row_dict)
                    
                    results.append({
                        "description": description,
                        "columns": columns,
                        "data": data,
                        "row_count": len(data)
                    })
                    
            except Exception as e:
                logger.error(f"Error executing query: {e}")
                results.append({
                    "description": description,
                    "error": str(e),
                    "data": []
                })
        
        return results

    def process_multicomponent_data(self, response_data: dict) -> dict:
        """Process and enhance data for multicomponent rendering"""
        try:
            components = response_data.get('components', [])
            dataset = response_data.get('dataset', [])
            
            # Create a mapping of query IDs to their data
            query_data_map = {}
            for query_result in dataset:
                # Use description as fallback if no ID is provided
                query_id = query_result.get('id', query_result.get('description', ''))
                query_data_map[query_id] = query_result
            
            # Process each component and attach relevant data
            for i, component in enumerate(components):
                component_type = component.get('type', '')
                
                # Use first available dataset if no specific data source
                component_data = dataset[0] if dataset else None
                
                if component_data:
                    # For frontend compatibility, ensure component has required structure
                    if not component.get('id'):
                        component['id'] = f"comp_{i+1}"
                    
                    # Process based on component type matching frontend expectations
                    if component_type in ['bar_chart', 'line_chart', 'pie_chart']:
                        # Chart components - no additional processing needed, frontend handles it
                        pass
                    elif component_type in ['data_table', 'table']:
                        # Table components - no additional processing needed, frontend handles it
                        pass
                    elif component_type in ['metric_card', 'stat', 'card']:
                        # Metric components - no additional processing needed, frontend handles it
                        pass
                    elif component_type == 'list':
                        # List components - no additional processing needed, frontend handles it
                        pass
                    elif component_type == 'insights_panel':
                        # Insights panel uses the insights object directly
                        pass
                else:
                    # No data available
                    if not component.get('id'):
                        component['id'] = f"comp_{i+1}"
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing multicomponent data: {e}")
            return response_data
    
    def optimize_dataset(self, dataset: list) -> list:
        """Optimize dataset by removing unnecessary fields and limiting data size"""
        optimized_dataset = []
        
        for query_result in dataset:
            data = query_result.get('data', [])
            
            # Limit data size - frontend components typically don't need more than 1000 rows
            limited_data = data[:1000] if len(data) > 1000 else data
            
            # Keep only essential fields
            optimized_result = {
                'data': limited_data,
                'columns': query_result.get('columns', []),
                'row_count': len(limited_data),
                'description': query_result.get('description', '')
            }
            
            # Remove any error field if data is present
            if limited_data:
                optimized_result.pop('error', None)
            
            optimized_dataset.append(optimized_result)
        
        return optimized_dataset
    
    def cleanup_response(self, response_data: dict) -> dict:
        """Remove unnecessary fields from response to reduce size"""
        # Keep only essential fields for frontend
        essential_fields = {
            'success': response_data.get('success', True),
            'layout': response_data.get('layout', {}),
            'components': response_data.get('components', []),
            'dataset': response_data.get('dataset', []),
            'insights': response_data.get('insights', {})
        }
        
        # Clean up components - remove verbose descriptions if too long
        if essential_fields['components']:
            for component in essential_fields['components']:
                # Limit description length
                if component.get('description') and len(component['description']) > 100:
                    component['description'] = component['description'][:97] + '...'
                
                # Remove unnecessary properties
                component.pop('styling', None)
                
        # Clean up insights - limit array sizes
        if essential_fields['insights']:
            insights = essential_fields['insights']
            for key in ['key_findings', 'recommendations', 'next_steps', 'alerts']:
                if key in insights and isinstance(insights[key], list):
                    insights[key] = insights[key][:5]  # Limit to 5 items max
        
        return essential_fields
    
    def map_dataset_to_components(self, components, dataset):
        """Map dataset to components by component IDs with proper data processing"""
        if not components or not dataset:
            return {}
        
        dataset_by_component = {}
        
        # Use the first dataset for all components (most common case)
        base_dataset = dataset[0] if dataset else {}
        base_data = base_dataset.get('data', [])
        base_columns = base_dataset.get('columns', [])
        
        for component in components:
            component_id = component.get('id', f'component_{len(dataset_by_component) + 1}')
            component_type = component.get('type', '')
            
            # Process data based on component type
            processed_data = self._process_component_data(component, base_data, base_columns)
            
            # Only include component if it has meaningful data
            if processed_data and len(processed_data) > 0:
                dataset_by_component[component_id] = {
                    'data': processed_data,
                    'columns': base_columns,
                    'row_count': len(processed_data),
                    'description': base_dataset.get('description', f'Data for {component_type}')
                }
        
        return dataset_by_component
    
    def _process_component_data(self, component, data, columns):
        """Process data based on component type and properties"""
        component_type = component.get('type', '')
        properties = component.get('properties', {})
        
        # For pie_chart, we need aggregated data
        if component_type == 'pie_chart':
            data_field = properties.get('data_field', 'mental_health')
            if data_field in columns:
                # Aggregate data by the specified field
                aggregated = {}
                for row in data:
                    # Handle both dict and string data types
                    if isinstance(row, dict):
                        value = row.get(data_field, 'Unknown')
                    else:
                        # If row is not a dict, skip or handle appropriately
                        continue
                    aggregated[value] = aggregated.get(value, 0) + 1
                
                # Convert to format expected by pie chart
                return [{'label': k, 'value': v, data_field: k} for k, v in aggregated.items()]
        
        # For metric_card, calculate metrics
        elif component_type == 'metric_card':
            metrics = properties.get('metrics', [])
            metric_data = []
            
            for metric in metrics:
                field = metric.get('field', 'mental_health')
                filter_condition = metric.get('filter', '')
                aggregation = metric.get('aggregation', 'count')
                
                if aggregation == 'count':
                    if filter_condition:
                        # Parse filter condition like "mental_health='High'" or "primary_trigger='MH'"
                        if '=' in filter_condition:
                            filter_field, filter_value = filter_condition.split('=', 1)
                            filter_field = filter_field.strip()
                            filter_value = filter_value.strip().strip("'\"")
                            count = sum(1 for row in data if isinstance(row, dict) and row.get(filter_field) == filter_value)
                        else:
                            count = len(data)
                    else:
                        count = len(data)
                    metric_data.append({
                        'label': metric.get('label', 'Metric'),
                        'value': count,
                        'field': field
                    })
                elif aggregation == 'avg':
                    # For risk score calculation
                    risk_values = {'High': 3, 'Medium': 2, 'Low': 1}
                    total_score = sum(risk_values.get(row.get(field, 'Low'), 1) for row in data if isinstance(row, dict))
                    valid_rows = sum(1 for row in data if isinstance(row, dict))
                    avg_score = total_score / valid_rows if valid_rows > 0 else 0
                    metric_data.append({
                        'label': metric.get('label', 'Average'),
                        'value': round(avg_score, 2),
                        'field': field
                    })
            
            return metric_data
        
        # For data_table and insights_panel, return original data with all fields preserved
        return data



