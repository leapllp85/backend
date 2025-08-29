from django.core.management.base import BaseCommand
from django.db import connection
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Setup pgvector extension and knowledge base table'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up pgvector extension...'))
        
        try:
            with connection.cursor() as cursor:
                # Check if pgvector is available
                self.stdout.write('Checking for pgvector availability...')
                cursor.execute("SELECT name FROM pg_available_extensions WHERE name = 'vector';")
                available = cursor.fetchone()
                
                if not available:
                    self.stdout.write(self.style.WARNING('⚠️  pgvector extension not available in this PostgreSQL installation.'))
                    self.stdout.write('Creating knowledge base with TEXT field instead of vector...')
                    
                    # Drop existing table
                    cursor.execute('DROP TABLE IF EXISTS knowledge_base CASCADE;')
                    
                    # Create table without vector field
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
                    
                    self.stdout.write(self.style.SUCCESS('✅ Knowledge base created with TEXT embedding field (no vector similarity search)'))
                    return
                
                # Install pgvector extension
                self.stdout.write('Installing pgvector extension...')
                cursor.execute('CREATE EXTENSION IF NOT EXISTS vector;')
                
                # Drop existing knowledge_base table if it exists with wrong dimensions
                self.stdout.write('Dropping existing knowledge_base table if it exists...')
                cursor.execute('DROP TABLE IF EXISTS knowledge_base CASCADE;')
                
                # Create knowledge_base table with 1536 dimensions
                self.stdout.write('Creating knowledge_base table with 1536 dimensions...')
                cursor.execute('''
                    CREATE TABLE knowledge_base (
                        id SERIAL PRIMARY KEY,
                        content_id VARCHAR(100) NOT NULL,
                        content_type VARCHAR(50) NOT NULL,
                        title VARCHAR(255),
                        content TEXT NOT NULL,
                        metadata JSONB DEFAULT '{}',
                        embedding vector(1536),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
                # Create indexes
                self.stdout.write('Creating indexes...')
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_content_type_idx ON knowledge_base (content_type);')
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_content_id_idx ON knowledge_base (content_id);')
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_created_at_idx ON knowledge_base (created_at);')
                
                # Create vector similarity index
                cursor.execute('CREATE INDEX IF NOT EXISTS knowledge_base_embedding_idx ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);')
                
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
                
            self.stdout.write(self.style.SUCCESS('✅ pgvector extension and knowledge_base table setup completed successfully!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error setting up pgvector: {e}'))
            logger.error(f'pgvector setup failed: {e}')
