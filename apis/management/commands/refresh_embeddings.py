"""
Management command to generate or refresh embeddings in the knowledge base
Supports both pgvector and fallback Django model storage
"""
import os
import json
import logging
from typing import List, Dict, Any
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.conf import settings
from tqdm import tqdm

from apis.models.rag import KnowledgeBase
from apis.models import EmployeeProfile, Project, Course, Survey, ActionItem

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Generate or refresh embeddings in pgvector knowledge_base"

    def add_arguments(self, parser):
        parser.add_argument(
            '--content-type',
            type=str,
            help='Specific content type to refresh (e.g., "employee", "project", "survey")',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force refresh all embeddings, even existing ones',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Batch size for processing embeddings (default: 10)',
        )
        parser.add_argument(
            '--create-sample-data',
            action='store_true',
            help='Create sample knowledge base entries from existing data',
        )

    def handle(self, *args, **options):
        try:
            # Initialize embeddings
            embeddings = self.get_embeddings()
            if not embeddings:
                raise CommandError("HuggingFace embeddings not available. Please install required packages.")

            if options['create_sample_data']:
                self.create_sample_knowledge_base()

            # Get entries to process
            entries_to_process = self.get_entries_to_process(
                content_type=options.get('content_type'),
                force=options['force']
            )

            if not entries_to_process:
                self.stdout.write(self.style.SUCCESS("✅ No entries need embedding refresh."))
                return

            self.stdout.write(f"🧠 Processing {len(entries_to_process)} entries...")

            # Process in batches
            batch_size = options['batch_size']
            total_processed = 0
            total_errors = 0

            with tqdm(total=len(entries_to_process), desc="Generating embeddings") as pbar:
                for i in range(0, len(entries_to_process), batch_size):
                    batch = entries_to_process[i:i + batch_size]
                    processed, errors = self.process_batch(batch, embeddings)
                    total_processed += processed
                    total_errors += errors
                    pbar.update(len(batch))

            # Summary
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Embedding refresh complete. "
                    f"Processed: {total_processed}, Errors: {total_errors}"
                )
            )

        except Exception as e:
            logger.error(f"Error in refresh_embeddings command: {e}")
            raise CommandError(f"Command failed: {str(e)}")

    def get_embeddings(self):
        """Initialize HuggingFace embeddings"""
        try:
            from langchain_huggingface import HuggingFaceEmbeddings
            
            return HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={'device': 'cpu'},  # Use CPU for compatibility
                encode_kwargs={'normalize_embeddings': True}
            )
        except ImportError:
            self.stdout.write(
                self.style.WARNING("LangChain HuggingFace not available. Install with: pip install langchain-huggingface sentence-transformers")
            )
            return None
        except Exception as e:
            logger.error(f"Error initializing HuggingFace embeddings: {e}")
            return None

    def get_entries_to_process(self, content_type: str = None, force: bool = False) -> List[KnowledgeBase]:
        """Get knowledge base entries that need embedding processing"""
        queryset = KnowledgeBase.objects.all()

        if content_type:
            queryset = queryset.filter(content_type=content_type)

        if not force:
            # Only process entries without embeddings
            queryset = queryset.filter(embedding__in=['', '[]', None])

        return list(queryset.order_by('created_at'))

    def process_batch(self, batch: List[KnowledgeBase], embeddings) -> tuple[int, int]:
        """Process a batch of knowledge base entries"""
        processed = 0
        errors = 0

        try:
            with transaction.atomic():
                for entry in batch:
                    try:
                        # Generate embedding for content
                        if entry.content:
                            embedding_vector = embeddings.embed_query(entry.content)
                            entry.set_embedding_vector(embedding_vector)
                            entry.save(update_fields=['embedding', 'updated_at'])
                            processed += 1
                        else:
                            self.stdout.write(
                                self.style.WARNING(f"Skipping entry {entry.id}: no content")
                            )
                            errors += 1

                    except Exception as e:
                        logger.error(f"Error processing entry {entry.id}: {e}")
                        errors += 1

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            errors += len(batch)

        return processed, errors

    def create_sample_knowledge_base(self):
        """Create sample knowledge base entries from existing Django models"""
        self.stdout.write("📝 Creating sample knowledge base entries...")

        created_count = 0

        # Create employee entries
        try:
            for i, employee in enumerate(EmployeeProfile.objects.all()[:3]):
                KnowledgeBase.objects.create(
                    content_type='employee',
                    content_id=employee.id,
                    title=f"Employee Profile: {employee.user.get_full_name() or employee.user.username}",
                    content=f"Employee {employee.user.get_full_name() or employee.user.username}. "
                           f"Talent type: {employee.talent_type}. "
                           f"Mental health status: {employee.mental_health}. "
                           f"Motivation factor: {employee.motivation_factor}. "
                           f"Career opportunities: {employee.career_opportunities}.",
                    metadata={'talent_type': employee.talent_type, 'age': str(employee.age)}
                )
                created_count += 1
        except Exception as e:
            self.stdout.write(f"Error creating employee entries: {e}")

        # Create project entries  
        try:
            for i, project in enumerate(Project.objects.all()[:3]):
                KnowledgeBase.objects.create(
                    content_type='project',
                    content_id=project.id,
                    title=f"Project: {project.title}",
                    content=f"Project {project.title}: {project.description}. "
                           f"Status: {project.status}. Criticality: {project.criticality}. "
                           f"Start date: {project.start_date}. Go live date: {project.go_live_date}.",
                    metadata={'status': project.status, 'criticality': project.criticality}
                )
                created_count += 1
        except Exception as e:
            self.stdout.write(f"Error creating project entries: {e}")

        # Create survey entries
        try:
            for i, survey in enumerate(Survey.objects.all()[:3]):
                KnowledgeBase.objects.create(
                    content_type='survey',
                    content_id=survey.id,
                    title=f"Survey: {survey.title}",
                    content=f"Survey '{survey.title}': {survey.description}. "
                           f"Type: {survey.survey_type}. Status: {survey.status}. "
                           f"Target audience: {survey.target_audience}.",
                    metadata={'survey_type': survey.survey_type, 'status': survey.status}
                )
                created_count += 1
        except Exception as e:
            self.stdout.write(f"Error creating survey entries: {e}")

        # Create general HR policy entries
        try:
            # Add some sample HR policy entries
            policies = [
                {
                    'title': 'Remote Work Policy',
                    'content': 'Our company supports flexible remote work arrangements. Employees can work from home up to 3 days per week with manager approval. All remote work must maintain productivity standards and communication protocols.',
                    'metadata': {'policy_type': 'work_arrangement', 'category': 'flexibility'}
                },
                {
                    'title': 'Performance Review Process',
                    'content': 'Annual performance reviews are conducted every December. The process includes self-assessment, manager evaluation, and goal setting for the following year. Reviews focus on achievements, areas for improvement, and career development.',
                    'metadata': {'policy_type': 'performance', 'category': 'evaluation'}
                }
            ]
            
            for policy in policies:
                KnowledgeBase.objects.create(
                    content_type='policy',
                    content_id=created_count + 100,  # Use unique IDs
                    title=policy['title'],
                    content=policy['content'],
                    metadata=policy['metadata']
                )
                created_count += 1
        except Exception as e:
            self.stdout.write(f"Error creating policy entries: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"✅ Created {created_count} knowledge base entries")
        )
