from django.core.management.base import BaseCommand
from apis.services.rag_service import RAGService
from apis.models import KnowledgeBase
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Populate knowledge base with corporate data for RAG system'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force-refresh',
            action='store_true',
            help='Force refresh all existing knowledge base entries',
        )
        parser.add_argument(
            '--clear-first',
            action='store_true',
            help='Clear existing knowledge base before populating',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('🚀 Starting RAG Knowledge Base Population...')
        )
        
        # Initialize RAG service
        rag_service = RAGService()
        
        # Clear existing data if requested
        if options['clear_first']:
            self.stdout.write('🗑️  Clearing existing knowledge base...')
            count = KnowledgeBase.objects.count()
            KnowledgeBase.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'Deleted {count} existing knowledge base entries')
            )
        
        # Populate knowledge base
        self.stdout.write('📊 Extracting and embedding corporate data...')
        
        try:
            stats = rag_service.populate_knowledge_base(
                force_refresh=options['force_refresh']
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Knowledge Base Population Complete!\n'
                    f'   📝 Created: {stats["created"]} entries\n'
                    f'   🔄 Updated: {stats["updated"]} entries\n'
                    f'   ❌ Errors: {stats["errors"]} entries\n'
                    f'   📊 Total: {KnowledgeBase.objects.count()} entries in knowledge base'
                )
            )
            
            # Display summary by content type
            self.stdout.write('\n📈 Knowledge Base Summary by Content Type:')
            content_types = KnowledgeBase.objects.values_list('content_type', flat=True).distinct()
            for content_type in content_types:
                count = KnowledgeBase.objects.filter(content_type=content_type).count()
                self.stdout.write(f'   {content_type}: {count} entries')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Error populating knowledge base: {str(e)}')
            )
            logger.error(f'Knowledge base population error: {e}')
            
        self.stdout.write(
            self.style.SUCCESS(
                '\n🎯 RAG system is ready! Users can now query corporate data using natural language.'
            )
        )
