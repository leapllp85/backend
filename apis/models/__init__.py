# Import all models from their respective modules for clean organization

# Action Items
from .action_items import ActionItem

# Attrition
from .attrition import Attrition

# Projects
from .projects import Project

# Courses
from .courses import Course, CourseCategory

# Employees and Allocations
from .employees import EmployeeProfile, ProjectAllocation, Trigger

# Surveys
from .surveys import Survey, SurveyQuestion, SurveyResponse, SurveyAnswer

# RAG System
from .rag import KnowledgeBase

# Conversations
from .conversations import Conversation, ConversationMessage, ConversationShare

# Export all models for easy importing
__all__ = [
    # Action Items
    'ActionItem',
    
    # Attrition
    'Attrition',
    
    # Projects
    'Project',
    
    # Courses
    'Course',
    'CourseCategory',
    
    # Employees
    'EmployeeProfile',
    'ProjectAllocation',
    'Trigger',
    
    # Surveys
    'Survey',
    'SurveyQuestion',
    'SurveyResponse',
    'SurveyAnswer',
    
    # RAG System
    'KnowledgeBase',
    
    # Conversations
    'Conversation',
    'ConversationMessage',
    'ConversationShare',
]

# Set up cache invalidation signals
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver([post_save, post_delete], sender=EmployeeProfile)
@receiver([post_save, post_delete], sender=Project)
@receiver([post_save, post_delete], sender=ProjectAllocation)
@receiver([post_save, post_delete], sender=Course)
@receiver([post_save, post_delete], sender=Survey)
@receiver([post_save, post_delete], sender=ActionItem)
def invalidate_llm_cache(sender, instance, **kwargs):
    """Invalidate LLM cache when relevant data changes"""
    try:
        from apis.views.cache_management import invalidate_cache_on_data_change
        invalidate_cache_on_data_change(sender, instance, **kwargs)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in cache invalidation signal: {e}")
