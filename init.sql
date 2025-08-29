-- Database initialization script for Corporate MVP with pgvector RAG setup
-- This script ensures the database and user exist for Docker deployment

-- Create database if it doesn't exist
SELECT 'CREATE DATABASE corporate_mvp'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'corporate_mvp')\gexec

-- Grant all privileges to the user
GRANT ALL PRIVILEGES ON DATABASE corporate_mvp TO leapllp112;

-- Connect to the corporate_mvp database
\c corporate_mvp;

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Set timezone
SET timezone = 'UTC';

-- Create knowledge base table for RAG
CREATE TABLE IF NOT EXISTS knowledge_base (
    id SERIAL PRIMARY KEY,
    content_id VARCHAR(255) NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    title VARCHAR(500),
    content TEXT NOT NULL,
    metadata JSONB,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for efficient vector search
CREATE INDEX IF NOT EXISTS knowledge_base_embedding_idx ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS knowledge_base_content_type_idx ON knowledge_base (content_type);
CREATE INDEX IF NOT EXISTS knowledge_base_content_id_idx ON knowledge_base (content_id);
CREATE INDEX IF NOT EXISTS knowledge_base_metadata_idx ON knowledge_base USING gin (metadata);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for updated_at
CREATE TRIGGER update_knowledge_base_updated_at BEFORE UPDATE ON knowledge_base FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
