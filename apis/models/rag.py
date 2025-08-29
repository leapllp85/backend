from django.db import models
import json

class KnowledgeBase(models.Model):
    """
    Knowledge base for RAG system with fallback for systems without pgvector
    Stores embeddings of corporate data for semantic search
    """
    
    # Content identification
    content_type = models.CharField(max_length=50, help_text="Type of content (e.g., 'project', 'employee', 'survey')")
    content_id = models.CharField(max_length=100, help_text="ID of the source content")
    title = models.CharField(max_length=255, help_text="Title or summary of the content")
    content = models.TextField(help_text="Full text content for embedding")
    
    # Vector embedding stored as TEXT (fallback for systems without pgvector)
    embedding = models.TextField(help_text="Vector embedding of the content stored as JSON")
    
    # Metadata for filtering and context
    metadata = models.JSONField(default=dict, help_text="Additional metadata for filtering and context")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'knowledge_base'
        indexes = [
            models.Index(fields=['content_type']),
            models.Index(fields=['content_id']),
            models.Index(fields=['created_at']),
        ]
        # Vector similarity index is created in init.sql
    
    def __str__(self):
        return f"{self.content_type}: {self.title}"
    
    def get_embedding_vector(self):
        """Convert stored embedding text back to list of floats"""
        try:
            return json.loads(self.embedding) if self.embedding else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_embedding_vector(self, embedding_list):
        """Store embedding list as JSON text"""
        self.embedding = json.dumps(embedding_list) if embedding_list else "[]"
    
    def to_context_dict(self):
        """Convert to dictionary for RAG context"""
        return {
            'content_type': self.content_type,
            'content_id': self.content_id,
            'title': self.title,
            'content': self.content,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    @classmethod
    def search_similar(cls, query_embedding, limit=10, threshold=0.5, content_type=None):
        """
        Search for similar content using cosine similarity (fallback without pgvector)
        
        Args:
            query_embedding: Vector embedding of the query
            limit: Maximum number of results to return
            threshold: Minimum similarity threshold (0-1)
            content_type: Optional filter by content type
            
        Returns:
            List of similar KnowledgeBase entries with similarity scores
        """
        import numpy as np
        
        # Get all entries (with optional content type filter)
        queryset = cls.objects.all()
        if content_type:
            if isinstance(content_type, list):
                queryset = queryset.filter(content_type__in=content_type)
            else:
                queryset = queryset.filter(content_type=content_type)
        
        results = []
        query_vector = np.array(query_embedding)
        query_norm = np.linalg.norm(query_vector)
        
        if query_norm == 0:
            return results
        
        for entry in queryset:
            try:
                entry_embedding = entry.get_embedding_vector()
                if not entry_embedding:
                    continue
                
                entry_vector = np.array(entry_embedding)
                entry_norm = np.linalg.norm(entry_vector)
                
                if entry_norm == 0:
                    continue
                
                # Calculate cosine similarity
                similarity = np.dot(query_vector, entry_vector) / (query_norm * entry_norm)
                
                if similarity >= threshold:
                    # Create result object with similarity attribute
                    entry.similarity = float(similarity)
                    results.append(entry)
                    
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        
        # Sort by similarity (descending) and limit results
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:limit]
