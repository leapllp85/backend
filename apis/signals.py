from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.core.cache import caches
from .models import (
    EmployeeProfile, Project, Survey, Course, ActionItem, KnowledgeBase, ProjectAllocation
)
from .services.rag_service import RAGService
import logging

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Project)
def update_project_knowledge_base(sender, instance, created, **kwargs):
    """Update knowledge base when Project is created or updated"""
    try:
        rag_service = RAGService()
        
        # Remove existing entry if updating
        if not created:
            KnowledgeBase.objects.filter(
                content_type='project',
                content_id=str(instance.id)
            ).delete()
        
        # Create content for knowledge base
        content = f"""
        Project: {instance.title}
        Description: {instance.description}
        Status: {instance.status}
        Criticality: {instance.criticality}
        Start Date: {instance.start_date}
        Go Live Date: {instance.go_live_date}
        Team Size: {instance.assigned_to.count()}
        Source: {instance.source}
        """
        
        # Add to knowledge base
        rag_service.add_to_knowledge_base(
            content=content.strip(),
            source=f"project_{instance.id}",
            metadata={
                'type': 'project',
                'project_id': instance.id,
                'title': instance.title,
                'status': instance.status,
                'criticality': instance.criticality
            }
        )
        
        logger.info(f"Updated knowledge base for project: {instance.title}")
        
    except Exception as e:
        logger.error(f"Error updating knowledge base for project {instance.id}: {e}")


@receiver(post_delete, sender=Project)
def delete_project_knowledge_base(sender, instance, **kwargs):
    """Remove project from knowledge base when deleted"""
    try:
        KnowledgeBase.objects.filter(
            content_type='project',
            content_id=str(instance.id)
        ).delete()
        
        logger.info(f"Removed project {instance.title} from knowledge base")
        
    except Exception as e:
        logger.error(f"Error removing project {instance.id} from knowledge base: {e}")


@receiver(post_save, sender=EmployeeProfile)
def update_employee_knowledge_base(sender, instance, created, **kwargs):
    """Update knowledge base when EmployeeProfile is created or updated"""
    try:
        rag_service = RAGService()
        
        # Remove existing entry if updating
        if not created:
            KnowledgeBase.objects.filter(
                content_type='employee',
                content_id=str(instance.user.id)
            ).delete()
        
        # Create content for knowledge base (non-sensitive data only)
        content = f"""
        Employee: {instance.user.first_name} {instance.user.last_name}
        Role: {instance.role}
        Age: {instance.age}
        Is Manager: {instance.is_manager}
        Manager: {instance.manager.username if instance.manager else 'None'}
        Risk Assessment: {instance.manager_assessment_risk}
        Mental Health: {instance.mental_health}
        Motivation Factor: {instance.motivation_factor}
        Career Opportunities: {instance.career_opportunities}
        Personal Reason: {instance.personal_reason}
        """
        
        # Add to knowledge base
        rag_service.add_to_knowledge_base(
            content=content.strip(),
            source=f"employee_{instance.user.id}",
            metadata={
                'type': 'employee',
                'user_id': instance.user.id,
                'role': instance.role,
                'is_manager': instance.is_manager,
                'manager_id': instance.manager.id if instance.manager else None
            }
        )
        
        logger.info(f"Updated knowledge base for employee: {instance.user.username}")
        
    except Exception as e:
        logger.error(f"Error updating knowledge base for employee {instance.user.id}: {e}")
    


@receiver(post_delete, sender=EmployeeProfile)
def delete_employee_knowledge_base(sender, instance, **kwargs):
    """Remove employee from knowledge base when deleted"""
    try:
        KnowledgeBase.objects.filter(
            content_type='employee',
            content_id=str(instance.user.id)
        ).delete()
        
        logger.info(f"Removed employee {instance.user.username} from knowledge base")
        
    except Exception as e:
        logger.error(f"Error removing employee {instance.user.id} from knowledge base: {e}")
    


@receiver(post_save, sender=Survey)
def update_survey_knowledge_base(sender, instance, created, **kwargs):
    """Update knowledge base when Survey is created or updated"""
    try:
        rag_service = RAGService()
        
        # Remove existing entry if updating
        if not created:
            KnowledgeBase.objects.filter(
                content_type='survey',
                content_id=str(instance.id)
            ).delete()
        
        # Create content for knowledge base
        content = f"""
        Survey: {instance.title}
        Description: {instance.description}
        Status: {instance.status}
        Created By: {instance.created_by.username}
        Assigned Count: {instance.assigned_to.count()}
        Questions Count: {instance.questions.count()}
        Created Date: {instance.created_at}
        """
        
        # Add to knowledge base
        rag_service.add_to_knowledge_base(
            content=content.strip(),
            source=f"survey_{instance.id}",
            metadata={
                'type': 'survey',
                'survey_id': instance.id,
                'title': instance.title,
                'status': instance.status,
                'created_by': instance.created_by.username
            }
        )
        
        logger.info(f"Updated knowledge base for survey: {instance.title}")
        
    except Exception as e:
        logger.error(f"Error updating knowledge base for survey {instance.id}: {e}")


@receiver(post_delete, sender=Survey)
def delete_survey_knowledge_base(sender, instance, **kwargs):
    """Remove survey from knowledge base when deleted"""
    try:
        KnowledgeBase.objects.filter(
            content_type='survey',
            content_id=str(instance.id)
        ).delete()
        
        logger.info(f"Removed survey {instance.title} from knowledge base")
        
    except Exception as e:
        logger.error(f"Error removing survey {instance.id} from knowledge base: {e}")


@receiver(post_save, sender=Course)
def update_course_knowledge_base(sender, instance, created, **kwargs):
    """Update knowledge base when Course is created or updated"""
    try:
        rag_service = RAGService()
        
        # Remove existing entry if updating
        if not created:
            KnowledgeBase.objects.filter(
                content_type='course',
                content_id=str(instance.id)
            ).delete()
        
        # Create content for knowledge base
        content = f"""
        Course: {instance.title}
        Description: {instance.description}
        Category: {instance.category.name if instance.category else 'None'}
        Duration: {instance.duration_hours} hours
        Difficulty: {instance.difficulty_level}
        Assigned Count: {instance.assigned_to.count()}
        Created Date: {instance.created_at}
        """
        
        # Add to knowledge base
        rag_service.add_to_knowledge_base(
            content=content.strip(),
            source=f"course_{instance.id}",
            metadata={
                'type': 'course',
                'course_id': instance.id,
                'title': instance.title,
                'category': instance.category.name if instance.category else None,
                'difficulty': instance.difficulty_level
            }
        )
        
        logger.info(f"Updated knowledge base for course: {instance.title}")
        
    except Exception as e:
        logger.error(f"Error updating knowledge base for course {instance.id}: {e}")


@receiver(post_delete, sender=Course)
def delete_course_knowledge_base(sender, instance, **kwargs):
    """Remove course from knowledge base when deleted"""
    try:
        KnowledgeBase.objects.filter(
            content_type='course',
            content_id=str(instance.id)
        ).delete()
        
        logger.info(f"Removed course {instance.title} from knowledge base")
        
    except Exception as e:
        logger.error(f"Error removing course {instance.id} from knowledge base: {e}")


@receiver(post_save, sender=ActionItem)
def update_action_item_knowledge_base(sender, instance, created, **kwargs):
    """Update knowledge base when ActionItem is created or updated"""
    try:
        rag_service = RAGService()
        
        # Remove existing entry if updating
        if not created:
            KnowledgeBase.objects.filter(
                content_type='action_item',
                content_id=str(instance.id)
            ).delete()
        
        # Create content for knowledge base
        content = f"""
        Action Item: {instance.title}
        Description: {instance.description}
        Priority: {instance.priority}
        Status: {instance.status}
        Assigned To: {instance.assigned_to.username}
        Created By: {instance.created_by.username}
        Due Date: {instance.due_date}
        Created Date: {instance.created_at}
        """
        
        # Add to knowledge base
        rag_service.add_to_knowledge_base(
            content=content.strip(),
            source=f"action_item_{instance.id}",
            metadata={
                'type': 'action_item',
                'action_item_id': instance.id,
                'title': instance.title,
                'priority': instance.priority,
                'status': instance.status,
                'assigned_to': instance.assigned_to.username
            }
        )
        
        logger.info(f"Updated knowledge base for action item: {instance.title}")
        
    except Exception as e:
        logger.error(f"Error updating knowledge base for action item {instance.id}: {e}")


@receiver(post_delete, sender=ActionItem)
def delete_action_item_knowledge_base(sender, instance, **kwargs):
    """Remove action item from knowledge base when deleted"""
    try:
        KnowledgeBase.objects.filter(
            content_type='action_item',
            content_id=str(instance.id)
        ).delete()
        
        logger.info(f"Removed action item {instance.title} from knowledge base")
        
    except Exception as e:
        logger.error(f"Error removing action item {instance.id} from knowledge base: {e}")


# Bulk update signal for when multiple records need to be updated
def bulk_update_knowledge_base():
    """Manually trigger bulk update of knowledge base"""
    try:
        rag_service = RAGService()
        
        # Clear existing knowledge base
        KnowledgeBase.objects.all().delete()
        
        # Repopulate from all models
        stats = rag_service.populate_knowledge_base()
        
        logger.info(f"Bulk updated knowledge base: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Error in bulk knowledge base update: {e}")
        return {'errors': 1, 'success': 0}


# Cache invalidation signals for project allocations
@receiver(post_save, sender=ProjectAllocation)
def invalidate_project_allocation_cache(sender, instance, created, **kwargs):
    """Handle project allocation creation or update"""
    pass


@receiver(post_delete, sender=ProjectAllocation)
def invalidate_project_allocation_delete_cache(sender, instance, **kwargs):
    """Handle project allocation deletion"""
    pass


# Project signals
@receiver(post_save, sender=Project)
def handle_project_save(sender, instance, created, **kwargs):
    """Handle project creation or update"""
    pass


@receiver(post_delete, sender=Project)
def handle_project_delete(sender, instance, **kwargs):
    """Handle project deletion"""
    pass


# User model changes
@receiver(post_save, sender=User)
def handle_user_save(sender, instance, created, **kwargs):
    """Handle user profile updates"""
    pass




def invalidate_all_team_caches():
    """Legacy function - no longer needed"""
    pass
