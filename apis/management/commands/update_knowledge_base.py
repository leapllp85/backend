from django.core.management.base import BaseCommand
from apis.signals import bulk_update_knowledge_base
from apis.services.rag_service import RAGService
from apis.models import KnowledgeBase
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update the RAG knowledge base with current model data'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing knowledge base before updating'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--content-type',
            type=str,
            choices=['project', 'employee', 'survey', 'course', 'action_item'],
            help='Update only specific content type'
        )
    
    def handle(self, *args, **options):
        clear_existing = options['clear']
        dry_run = options['dry_run']
        content_type = options['content_type']
        
        self.stdout.write(
            self.style.SUCCESS('🧠 Updating RAG Knowledge Base...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('⚠️  DRY RUN MODE - No changes will be made')
            )
        
        try:
            rag_service = RAGService()
            
            # Show current state
            current_count = KnowledgeBase.objects.count()
            self.stdout.write(f'📊 Current knowledge base entries: {current_count}')
            
            if content_type:
                current_type_count = KnowledgeBase.objects.filter(
                    content_type=content_type
                ).count()
                self.stdout.write(f'📊 Current {content_type} entries: {current_type_count}')
            
            if not dry_run:
                if clear_existing:
                    if content_type:
                        # Clear only specific content type
                        deleted_count = KnowledgeBase.objects.filter(
                            content_type=content_type
                        ).count()
                        KnowledgeBase.objects.filter(content_type=content_type).delete()
                        self.stdout.write(f'🗑️  Cleared {deleted_count} {content_type} entries')
                    else:
                        # Clear all
                        KnowledgeBase.objects.all().delete()
                        self.stdout.write('🗑️  Cleared all existing knowledge base entries')
                
                # Update knowledge base
                if content_type:
                    stats = self._update_specific_content_type(rag_service, content_type)
                else:
                    stats = bulk_update_knowledge_base()
                
                # Display results
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('✅ Knowledge base update completed!'))
                self.stdout.write(f'📈 Statistics:')
                self.stdout.write(f'   ✅ Successful updates: {stats.get("success", 0)}')
                self.stdout.write(f'   ❌ Errors: {stats.get("errors", 0)}')
                
                # Show final state
                final_count = KnowledgeBase.objects.count()
                self.stdout.write(f'📊 Final knowledge base entries: {final_count}')
                
                if content_type:
                    final_type_count = KnowledgeBase.objects.filter(
                        content_type=content_type
                    ).count()
                    self.stdout.write(f'📊 Final {content_type} entries: {final_type_count}')
            
            else:
                # Dry run - show what would be updated
                self.stdout.write('📋 Dry run results:')
                
                from apis.models import Project, EmployeeProfile, Survey, Course, ActionItem
                
                models_to_check = []
                if not content_type or content_type == 'project':
                    models_to_check.append(('project', Project))
                if not content_type or content_type == 'employee':
                    models_to_check.append(('employee', EmployeeProfile))
                if not content_type or content_type == 'survey':
                    models_to_check.append(('survey', Survey))
                if not content_type or content_type == 'course':
                    models_to_check.append(('course', Course))
                if not content_type or content_type == 'action_item':
                    models_to_check.append(('action_item', ActionItem))
                
                total_would_update = 0
                for type_name, model_class in models_to_check:
                    count = model_class.objects.count()
                    self.stdout.write(f'   {type_name}: {count} entries would be updated')
                    total_would_update += count
                
                self.stdout.write(f'📊 Total entries that would be updated: {total_would_update}')
            
            self.stdout.write('')
            self.stdout.write('🎉 Knowledge base update process completed!')
            
        except Exception as e:
            logger.error(f"Error updating knowledge base: {e}")
            self.stdout.write(
                self.style.ERROR(f'❌ Knowledge base update failed: {str(e)}')
            )
    
    def _update_specific_content_type(self, rag_service, content_type):
        """Update knowledge base for a specific content type"""
        stats = {'success': 0, 'errors': 0}
        
        try:
            if content_type == 'project':
                from apis.models import Project
                for project in Project.objects.all():
                    try:
                        content = f"""
                        Project: {project.title}
                        Description: {project.description}
                        Status: {project.status}
                        Criticality: {project.criticality}
                        Start Date: {project.start_date}
                        Go Live Date: {project.go_live_date}
                        Team Size: {project.assigned_to.count()}
                        Source: {project.source}
                        """
                        
                        rag_service.add_to_knowledge_base(
                            content=content.strip(),
                            source=f"project_{project.id}",
                            metadata={
                                'type': 'project',
                                'project_id': project.id,
                                'title': project.title,
                                'status': project.status,
                                'criticality': project.criticality
                            }
                        )
                        stats['success'] += 1
                    except Exception as e:
                        logger.error(f"Error updating project {project.id}: {e}")
                        stats['errors'] += 1
            
            elif content_type == 'employee':
                from apis.models import EmployeeProfile
                for profile in EmployeeProfile.objects.select_related('user').all():
                    try:
                        content = f"""
                        Employee: {profile.user.first_name} {profile.user.last_name}
                        Role: {profile.role}
                        Age: {profile.age}
                        Is Manager: {profile.is_manager}
                        Manager: {profile.manager.username if profile.manager else 'None'}
                        Risk Assessment: {profile.manager_assessment_risk}
                        """
                        
                        rag_service.add_to_knowledge_base(
                            content=content.strip(),
                            source=f"employee_{profile.user.id}",
                            metadata={
                                'type': 'employee',
                                'user_id': profile.user.id,
                                'role': profile.role,
                                'is_manager': profile.is_manager
                            }
                        )
                        stats['success'] += 1
                    except Exception as e:
                        logger.error(f"Error updating employee {profile.user.id}: {e}")
                        stats['errors'] += 1
            
            # Add similar blocks for other content types...
            
        except Exception as e:
            logger.error(f"Error in specific content type update: {e}")
            stats['errors'] += 1
        
        return stats
