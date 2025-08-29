from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from apis.permissions import IsManagerOrAssociate
from apis.models import EmployeeProfile
from apis.services.rag_service import RAGService
from anthropic import Anthropic
from django.conf import settings
import json
import logging

logger = logging.getLogger(__name__)

class ChatAPIView(APIView):
    """RAG-powered chat API with Anthropic Claude Sonnet 4 for versatile HTML generation"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rag_service = RAGService()
        self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def post(self, request, *args, **kwargs):
        user_prompt = request.data.get("prompt", "").strip()
        if not user_prompt:
            return HttpResponse(
                self.generate_error_html("Missing prompt. Please provide a query."),
                content_type='text/html'
            )

        user = request.user
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return HttpResponse(
                self.generate_error_html("Employee profile not found."),
                content_type='text/html'
            )

        try:
            # Step 1: Search knowledge base for relevant context
            logger.info(f"Searching knowledge base for query: {user_prompt}")
            context_data = self.rag_service.search_knowledge_base(
                query=user_prompt,
                limit=15,
                threshold=0.6
            )
            
            # Step 2: Apply role-based filtering to context
            filtered_context = self.rag_service.get_role_filtered_context(
                user, user_profile, context_data
            )
            
            if not filtered_context:
                return HttpResponse(
                    self.generate_error_html(
                        "No relevant information found for your query. Try rephrasing or asking about projects, employees, courses, or surveys."
                    ),
                    content_type='text/html'
                )
            
            # Step 3: Generate versatile HTML response using Claude Sonnet 4
            html_response = self.generate_claude_html_response(
                user_prompt, filtered_context, user_profile
            )
            
            return HttpResponse(html_response, content_type='text/html')
            
        except Exception as e:
            logger.error(f"Error in ChatAPIView: {e}")
            return HttpResponse(
                self.generate_error_html(f"An error occurred while processing your request: {str(e)}"),
                content_type='text/html'
            )

    def generate_claude_html_response(self, user_query: str, context_data: list, user_profile) -> str:
        """Generate versatile HTML response using Claude Sonnet 4 with RAG context"""
        
        # Prepare context summary for Claude
        context_summary = self.prepare_context_for_claude(context_data)
        
        # Create comprehensive prompt for Claude Sonnet 4
        claude_prompt = f"""
You are an expert corporate data analyst and web developer. Generate a comprehensive, visually appealing HTML response for the following user query using the provided corporate data context.

User Query: "{user_query}"

User Role: {'Manager' if user_profile.is_manager else 'Associate'}

Relevant Corporate Data Context:
{context_summary}

Instructions:
1. Create a complete HTML response that directly answers the user's query
2. Be versatile - use the most appropriate format:
   - Tables for structured data comparisons
   - Charts/graphs for trends and analytics (use Chart.js or similar)
   - Cards for individual items or summaries
   - Lists for action items or recommendations
   - Plain text for explanations or insights

3. Include modern CSS styling with:
   - Professional corporate color scheme (blues, grays, whites)
   - Responsive design
   - Clean typography
   - Proper spacing and layout

4. If creating charts, use Chart.js CDN and include interactive features
5. Make the response actionable - include insights, recommendations, or next steps
6. Ensure the HTML is complete and self-contained
7. Use semantic HTML elements
8. Include relevant icons or visual elements where appropriate

Generate ONLY the HTML content (no explanations or markdown). The HTML should be ready to display directly in a browser.
"""
        
        # Call Claude Sonnet 4 for HTML generation using official client
        try:
            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4000,
                temperature=0.3,
                messages=[
                    {
                        "role": "user",
                        "content": claude_prompt
                    }
                ]
            )
            
            # Extract HTML content from response
            html_content = message.content[0].text.strip() if message.content else ""
            
            # Ensure we have valid HTML content
            if not html_content or len(html_content) < 50:
                return self.generate_error_html("Failed to generate response content")
                
            return html_content
                
        except Exception as e:
            logger.error(f"Claude API call error: {e}")
            return self.generate_error_html(f"Error generating response: {str(e)}")
    
    def prepare_context_for_claude(self, context_data: list) -> str:
        """Prepare context data for Claude in a structured format"""
        if not context_data:
            return "No relevant data found."
            
        context_lines = []
        
        # Group context by content type
        grouped_context = {}
        for item in context_data:
            content_type = item.get('content_type', 'unknown')
            if content_type not in grouped_context:
                grouped_context[content_type] = []
            grouped_context[content_type].append(item)
        
        # Format each group
        for content_type, items in grouped_context.items():
            context_lines.append(f"\n{content_type.upper()} DATA:")
            for i, item in enumerate(items[:5], 1):  # Limit to top 5 per type
                title = item.get('title', 'No title')
                content = item.get('content', '')[:200] + '...' if len(item.get('content', '')) > 200 else item.get('content', '')
                similarity = item.get('similarity', 0.0)
                context_lines.append(f"{i}. {title} (Relevance: {similarity:.2f})")
                context_lines.append(f"   Content: {content}")
                
                # Add metadata if available
                metadata = item.get('metadata', {})
                if metadata:
                    context_lines.append(f"   Details: {json.dumps(metadata, default=str)}")
                context_lines.append("")
        
        return "\n".join(context_lines)

    def generate_error_html(self, error_message: str) -> str:
        """Generate HTML error response"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Query Error</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .error {{ background: #fee; border: 1px solid #fcc; border-radius: 8px; padding: 20px; text-align: center; }}
                .error h2 {{ color: #c33; margin: 0 0 10px 0; }}
                .error p {{ color: #666; margin: 0; }}
                .icon {{ font-size: 48px; margin-bottom: 15px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error">
                    <div class="icon">⚠️</div>
                    <h2>Query Error</h2>
                    <p>{error_message}</p>
                </div>
            </div>
        </body>
        </html>
        """


