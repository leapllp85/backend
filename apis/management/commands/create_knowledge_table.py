from django.core.management.base import BaseCommand
from django.db import connection
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Create knowledge_base table without pgvector dependency'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Creating knowledge_base table...'))
        
        try:
            with connection.cursor() as cursor:
                # Drop existing table if it exists
                self.stdout.write('Dropping existing knowledge_base table if it exists...')
                cursor.execute('DROP TABLE IF EXISTS knowledge_base CASCADE;')
                
                # Create knowledge_base table with TEXT embedding field
                self.stdout.write('Creating knowledge_base table with TEXT embedding field...')
                cursor.execute('''
                    CREATE TABLE knowledge_base (
                        id SERIAL PRIMARY KEY,
                        content_id VARCHAR(100) NOT NULL,
                        content_type VARCHAR(50) NOT NULL,
                        title VARCHAR(255),
                        content TEXT NOT NULL,
                        metadata JSONB DEFAULT '{}',
                        embedding TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
                # Create indexes
                self.stdout.write('Creating indexes...')
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_content_type_idx ON knowledge_base (content_type);')
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_content_id_idx ON knowledge_base (content_id);')
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_created_at_idx ON knowledge_base (created_at);')
                
                # Create update trigger function
                cursor.execute('''
                    CREATE OR REPLACE FUNCTION update_updated_at_column()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        NEW.updated_at = CURRENT_TIMESTAMP;
                        RETURN NEW;
                    END;
                    $$ language 'plpgsql';
                ''')
                
                # Create trigger
                cursor.execute('CREATE TRIGGER update_knowledge_base_updated_at BEFORE UPDATE ON knowledge_base FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();')
                
            self.stdout.write(self.style.SUCCESS('✅ Knowledge base table created successfully with TEXT embedding field!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error creating knowledge base table: {e}'))
            logger.error(f'Knowledge base table creation failed: {e}')
