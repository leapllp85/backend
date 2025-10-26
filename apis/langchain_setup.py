"""
LangChain setup for HR Conversational Analytics Chatbot
Initializes LLM, embeddings, vector store, and chains for orchestration
"""
import logging
from langchain.prompts import PromptTemplate
from langchain_anthropic import ChatAnthropic
from langchain_postgres import PGVector
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.schema import Document
from langchain_core.output_parsers import StrOutputParser
from django.conf import settings

logger = logging.getLogger(__name__)

# Environment variables with fallbacks
DATABASE_URL = getattr(settings, 'DATABASE_URL', None)
if not DATABASE_URL:
    # Construct from Django settings
    db_config = settings.DATABASES['default']
    DATABASE_URL = f"postgresql://{db_config['USER']}:{db_config['PASSWORD']}@{db_config['HOST']}:{db_config['PORT']}/{db_config['NAME']}"

ANTHROPIC_API_KEY = settings.ANTHROPIC_API_KEY

# Initialize HuggingFace embeddings (free, no API key required)
try:
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'},  # Use CPU for compatibility
        encode_kwargs={'normalize_embeddings': True}
    )
    logger.info("HuggingFace embeddings initialized successfully")
except Exception as e:
    logger.warning(f"Failed to initialize HuggingFace embeddings: {e}")
    embeddings = None

# Initialize vector store (with fallback to Django model)
vectorstore = None
if embeddings and DATABASE_URL:
    try:
        vectorstore = PGVector(
            embeddings=embeddings,
            connection=DATABASE_URL,
            collection_name="knowledge_base",
        )
        logger.info("PGVector initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize PGVector: {e}")
        vectorstore = None
else:
    vectorstore = None

# Initialize Claude Sonnet LLM
llm = None
if ANTHROPIC_API_KEY:
    try:
        llm = ChatAnthropic(
            model="claude-3-5-sonnet-20240620",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.1,
            max_tokens=4000
        )
        logger.info("Claude Sonnet initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Claude: {e}")
        llm = None
else:
    logger.warning("No ANTHROPIC_API_KEY found. LLM features will be limited.")

# MCP Chain - for structured data queries
mcp_prompt = PromptTemplate.from_template("""
You are an HR analytics assistant with access to structured employee data.
Use the available tools to answer this question accurately and concisely.
{{ ... }}
Available data includes:
- Employee profiles (performance, motivation, risk factors)
- Projects (status, allocations, budgets)
- Surveys (responses, ratings, feedback)
- Action items (tasks, priorities, deadlines)
- Attrition data (risk levels, factors)

Question: {question}

Provide a clear, data-driven response based on the structured information available.
""")

mcp_chain = None
if llm:
    mcp_chain = mcp_prompt | llm | StrOutputParser()

# RAG Chain - for unstructured knowledge base queries
rag_prompt = PromptTemplate.from_template("""
You are an empathetic HR assistant helping with workplace questions.
Use the provided context to give helpful, supportive responses.

Context from knowledge base:
{context}

Question: {question}

Provide a thoughtful response that:
1. Addresses the question directly
2. Uses relevant information from the context
3. Maintains a supportive, professional tone
4. Suggests actionable next steps when appropriate
""")

rag_chain = None
if llm:
    rag_chain = rag_prompt | llm | StrOutputParser()

# Escalation Chain - for sensitive HR matters
escalation_prompt = PromptTemplate.from_template("""
You are a compassionate HR assistant handling a sensitive workplace matter.
This question requires careful, empathetic handling and may need human escalation.

Question: {question}

Provide a response that:
1. Acknowledges the sensitivity of the matter
2. Offers immediate support and resources
3. Clearly indicates when human HR intervention is needed
4. Maintains confidentiality and professionalism
5. Provides crisis resources if applicable

If this requires immediate human attention, start your response with "ESCALATE:"
""")

escalation_chain = None
if llm:
    escalation_chain = escalation_prompt | llm | StrOutputParser()

# Fallback search using Django model when pgvector is unavailable
def fallback_similarity_search(query: str, k: int = 3) -> list[Document]:
    """
    Fallback similarity search using Django KnowledgeBase model
    when pgvector is not available
    """
    if not embeddings:
        logger.warning("No embeddings available for similarity search")
        return []
    
    try:
        from .models.rag import KnowledgeBase
        
        # Generate query embedding using HuggingFace
        query_embedding = embeddings.embed_query(query)
        
        # Search using Django model
        similar_entries = KnowledgeBase.search_similar(
            query_embedding=query_embedding,
            limit=k,
            threshold=0.3  # Lower threshold for HuggingFace embeddings
        )
        
        # Convert to LangChain Documents
        documents = []
        for entry in similar_entries:
            doc = Document(
                page_content=entry.content,
                metadata={
                    'content_type': entry.content_type,
                    'content_id': entry.content_id,
                    'title': entry.title,
                    'similarity': getattr(entry, 'similarity', 0.0),
                    **entry.metadata
                }
            )
            documents.append(doc)
        
        return documents
        
    except Exception as e:
        logger.error(f"Fallback similarity search failed: {e}")
        return []

# Utility function to get similar documents
def get_similar_documents(query: str, k: int = 3) -> list[Document]:
    """
    Get similar documents using pgvector or fallback to Django model
    """
    if vectorstore:
        try:
            return vectorstore.similarity_search(query, k=k)
        except Exception as e:
            logger.warning(f"PGVector search failed, using fallback: {e}")
    
    return fallback_similarity_search(query, k=k)

# Health check function
def check_langchain_health() -> dict:
    """
    Check the health of all LangChain components
    """
    health = {
        'llm': llm is not None,
        'embeddings': embeddings is not None,
        'vectorstore': vectorstore is not None,
        'mcp_chain': mcp_chain is not None,
        'rag_chain': rag_chain is not None,
        'escalation_chain': escalation_chain is not None,
    }
    
    # Test LLM if available
    if llm:
        try:
            test_response = llm.invoke("Test message")
            health['llm_test'] = True
        except Exception as e:
            health['llm_test'] = False
            health['llm_error'] = str(e)
    
    return health

# Export main components
__all__ = [
    'llm',
    'embeddings', 
    'vectorstore',
    'mcp_chain',
    'rag_chain',
    'escalation_chain',
    'get_similar_documents',
    'check_langchain_health'
]
