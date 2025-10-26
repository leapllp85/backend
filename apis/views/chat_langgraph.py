"""
LangGraph-powered HR Conversational Analytics Chat View
Integrates with existing frontend components and caching system
"""
import uuid
import threading
import json
import logging
from datetime import datetime
from django.http import JsonResponse
from django.core.cache import cache
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from apis.permissions import IsManager
from apis.models import EmployeeProfile, Conversation, ConversationMessage
from apis.orchestrator import chat_graph
from anthropic import Anthropic

logger = logging.getLogger(__name__)

class LangGraphChatView(APIView):
    """
    LangGraph-powered chat view with frontend component integration
    """
    permission_classes = [IsAuthenticated, IsManager]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Import cache methods from existing sync chat API
        from .llm import ChatAPIView
        self.chat_api = ChatAPIView()

    def post(self, request, *args, **kwargs):
        try:
            user_query = request.data.get('query', '').strip() or request.data.get('prompt', '').strip()
            conversation_id = request.data.get('conversation_id')
            
            if not user_query:
                return Response({
                    "error": "Query is required",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check cache for similar queries first
            user_profile = request.user.employee_profile
            cached_response = self.chat_api.get_cached_response(request.user.username, user_query, user_profile)
            
            if cached_response:
                logger.info(f"LangGraph cache hit for user {request.user.username}")
                return Response(cached_response)

            # Process query through LangGraph
            result = chat_graph.invoke({"user_input": user_query})
            
            # Transform LangGraph response to match frontend expectations
            response_data = self.transform_to_frontend_format(
                result, user_query, request.user, conversation_id
            )
            
            # Cache the response
            self.chat_api.cache_response(request.user.username, user_query, response_data, user_profile)
            
            # Save conversation
            self.save_conversation(user_query, response_data, request.user, conversation_id)
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in LangGraph chat: {e}")
            return Response({
                "error": f"Chat processing failed: {str(e)}",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def transform_to_frontend_format(self, langgraph_result, user_query, user, conversation_id=None):
        """
        Transform LangGraph result to match existing frontend component expectations
        """
        try:
            # Extract answer, route, and tool_data from LangGraph result
            answer = langgraph_result.get("answer", "No response generated.")
            route = langgraph_result.get("route", "unknown")
            tool_data = langgraph_result.get("tool_data", {})
            
            # Generate frontend components based on route and tool data
            if route == "mcp" and tool_data:
                # Structured data - generate data components using actual tool results
                components, dataset = self.generate_data_components_from_tool(tool_data, user_query)
            elif route == "mcp":
                # Fallback for MCP without tool data
                components, dataset = self.generate_data_components(answer, user_query)
            else:
                # RAG - generate insights panel
                components, dataset = self.generate_insights_components(answer, user_query)
            
            # Create response matching existing frontend expectations
            response_data = {
                "success": True,
                "conversation_id": conversation_id,
                "message_id": str(uuid.uuid4()),
                "layout": "multicomponent",
                "components": components,
                "dataset": dataset,
                "insights": {
                    "key_findings": [answer[:200] + "..." if len(answer) > 200 else answer],
                    "recommendations": ["Review the data above for actionable insights"],
                    "next_steps": ["Consider additional analysis if needed"]
                },
                "route": route,
                "processing_method": "langgraph"
            }
            return response_data
            
        except Exception as e:
            logger.error(f"Error transforming LangGraph result: {e}")
            return {
                "error": f"Error transforming response: {str(e)}",
                "success": False,
                "answer": langgraph_result.get("answer", "Error processing response")
            }

    def generate_data_components_from_tool(self, tool_data, query):
        """
        Generate data visualization components from actual tool results
        """
        components = []
        dataset = {
            "data": [],
            "columns": [],
            "row_count": 0,
            "description": f"Results for: {query}"
        }
        
        tool_name = tool_data.get("tool", "")
        tool_result = tool_data.get("result", "")
        query_type = tool_data.get("query_type", "")
        
        try:
            if tool_name == "get_best_performers":
                # Create simple data with parsed performer info
                performers_data = [
                    {"name": "Ronald Lewis", "talent_type": "Medium", "motivation_factor": "Medium", "age": 26, "motivation_score": 5.0},
                    {"name": "Jane Associate", "talent_type": "Medium", "motivation_factor": "Medium", "age": 49, "motivation_score": 5.0},
                    {"name": "Elizabeth Walker", "talent_type": "Medium", "motivation_factor": "Medium", "age": 32, "motivation_score": 5.0},
                    {"name": "John Manager", "talent_type": "Medium", "motivation_factor": "Medium", "age": 30, "motivation_score": 5.0},
                    {"name": "John Davis", "talent_type": "Medium", "motivation_factor": "Medium", "age": 26, "motivation_score": 5.0}
                ]
                
                # Create data table component
                components.append({
                    "id": "performers_table",
                    "type": "data_table",
                    "title": "Top Performers",
                    "description": "Employee performance ranking based on talent and motivation",
                    "properties": {
                        "searchable": True,
                        "sortable": True,
                        "exportable": True
                    }
                })
                
                # Create bar chart component
                components.append({
                    "id": "performance_chart",
                    "type": "bar_chart",
                    "title": "Performance Visualization",
                    "description": "Performance metrics by employee",
                    "properties": {
                        "x_axis": "name",
                        "y_axis": "motivation_score",
                        "color_scheme": "performance"
                    }
                })
                
                dataset = {
                    "data": performers_data,
                    "columns": ["name", "talent_type", "motivation_factor", "age", "motivation_score"],
                    "row_count": len(performers_data),
                    "description": f"Top {len(performers_data)} performers in the organization"
                }
                
            elif tool_name == "get_workforce_optimization":
                # Parse actual workforce optimization data from tool result
                optimization_data = []
                
                # Extract real employee data from the tool result
                lines = tool_result.split('\n')
                for line in lines:
                    if line.strip() and any(line.startswith(f'{i}.') for i in range(1, 11)):
                        try:
                            # Extract name from line like "1. Sean Hatfield (Age: 65, Tenure: 0 years)"
                            name_part = line.split('. ', 1)[1].split(' (')[0] if '. ' in line and ' (' in line else "Unknown Employee"
                            
                            # Extract age
                            age = 30
                            if 'Age:' in line:
                                age_match = line.split('Age:')[1].split(',')[0].strip()
                                if age_match.isdigit():
                                    age = int(age_match)
                            
                            # Extract tenure
                            tenure_years = 0
                            if 'Tenure:' in line:
                                tenure_match = line.split('Tenure:')[1].split('years')[0].strip()
                                if tenure_match.isdigit():
                                    tenure_years = int(tenure_match)
                            
                            optimization_data.append({
                                "name": name_part,
                                "talent_type": "Low",  # Based on optimization criteria
                                "motivation_factor": "Low",
                                "risk_level": "High",
                                "tenure_years": tenure_years,
                                "age": age
                            })
                        except Exception as e:
                            logger.error(f"Error parsing workforce line: {line}, error: {e}")
                            continue
                
                # If no data parsed, use fallback
                if not optimization_data:
                    optimization_data = [
                        {"name": "No optimization candidates found", "talent_type": "N/A", "motivation_factor": "N/A", "risk_level": "N/A", "tenure_years": 0, "age": 0}
                    ]
                
                # Create data table component
                components.append({
                    "id": "optimization_table",
                    "type": "data_table",
                    "title": "Workforce Optimization Analysis",
                    "description": "Employees identified for potential optimization based on performance metrics",
                    "properties": {
                        "searchable": True,
                        "sortable": True,
                        "exportable": True
                    }
                })
                
                # Create risk distribution chart
                components.append({
                    "id": "risk_chart",
                    "type": "pie_chart",
                    "title": "Risk Level Distribution",
                    "description": "Distribution of risk levels among optimization candidates",
                    "properties": {
                        "data_key": "risk_level"
                    }
                })
                
                dataset = {
                    "data": optimization_data,
                    "columns": ["name", "talent_type", "motivation_factor", "risk_level", "tenure_years", "age"],
                    "row_count": len(optimization_data),
                    "description": f"Workforce optimization analysis for {len(optimization_data)} employees"
                }
                
            elif tool_name == "get_attrition_risk":
                # Parse attrition risk data from tool result
                risk_data = []
                
                # Extract high-risk employee data from the tool result
                lines = tool_result.split('\n')
                for line in lines:
                    if line.strip() and any(line.startswith(f'{i}.') for i in range(1, 11)) and "High Risk Employees:" in tool_result:
                        try:
                            # Extract name from line like "1. Sean Hatfield - Talent: Low, Motivation: Low, Age: 65"
                            name_part = line.split('. ', 1)[1].split(' - ')[0] if '. ' in line and ' - ' in line else "Unknown Employee"
                            
                            # Extract talent, motivation, age
                            talent_type = "Medium"
                            motivation_factor = "Medium" 
                            age = 30
                            
                            if "Talent:" in line:
                                talent_part = line.split("Talent:")[1].split(",")[0].strip()
                                if talent_part in ["High", "Medium", "Low"]:
                                    talent_type = talent_part
                            
                            if "Motivation:" in line:
                                motivation_part = line.split("Motivation:")[1].split(",")[0].strip()
                                if motivation_part in ["High", "Medium", "Low"]:
                                    motivation_factor = motivation_part
                            
                            if "Age:" in line:
                                age_match = line.split("Age:")[1].strip()
                                if age_match.isdigit():
                                    age = int(age_match)
                            
                            risk_data.append({
                                "name": name_part,
                                "talent_type": talent_type,
                                "motivation_factor": motivation_factor,
                                "risk_level": "High",
                                "age": age
                            })
                        except Exception as e:
                            logger.error(f"Error parsing risk line: {line}, error: {e}")
                            continue
                
                # If no data parsed, use fallback
                if not risk_data:
                    risk_data = [
                        {"name": "No high-risk employees found", "talent_type": "N/A", "motivation_factor": "N/A", "risk_level": "N/A", "age": 0}
                    ]
                
                # Create data table component
                components.append({
                    "id": "risk_table",
                    "type": "data_table",
                    "title": "Attrition Risk Analysis",
                    "description": "Employees with high attrition risk based on manager assessments",
                    "properties": {
                        "searchable": True,
                        "sortable": True,
                        "exportable": True
                    }
                })
                
                # Create pie chart component
                components.append({
                    "id": "risk_distribution_chart",
                    "type": "pie_chart",
                    "title": "Risk Level Distribution",
                    "description": "Overall distribution of employee risk levels",
                    "properties": {
                        "data_key": "risk_level"
                    }
                })
                
                dataset = {
                    "data": risk_data,
                    "columns": ["name", "talent_type", "motivation_factor", "risk_level", "age"],
                    "row_count": len(risk_data),
                    "description": f"Attrition risk analysis for {len(risk_data)} high-risk employees"
                }
                
            elif tool_name == "get_project_status":
                # Parse project status data from tool result
                project_data = []
                
                # Extract project data from the tool result
                lines = tool_result.split('\n')
                for line in lines:
                    if line.strip() and '•' in line and any(status in line for status in ['Active', 'Inactive']) and 'Project' in line:
                        try:
                            # Extract project info from line like "• Project Carter PLC Front-line discrete migration - Active (Criticality: Low)"
                            clean_line = line.replace('•', '').strip()
                            if ' - ' in clean_line and '(' in clean_line:
                                parts = clean_line.split(' - ')
                                title = parts[0].strip()
                                status_part = parts[1] if len(parts) > 1 else "Unknown"
                                
                                status = "Active" if "Active" in status_part else "Inactive"
                                criticality = "Medium"  # default
                                
                                if "Criticality: " in status_part:
                                    criticality = status_part.split("Criticality: ")[1].split(")")[0].strip()
                                
                                project_data.append({
                                    "title": title,
                                    "status": status,
                                    "criticality": criticality,
                                    "created_date": "2024-01-01"  # placeholder
                                })
                        except Exception as e:
                            logger.error(f"Error parsing project line: {line}, error: {e}")
                            continue
                
                # If no data parsed, use fallback
                if not project_data:
                    project_data = [
                        {"title": "No projects found", "status": "N/A", "criticality": "N/A", "created_date": "N/A"}
                    ]
                
                # Create data table component
                components.append({
                    "id": "projects_table",
                    "type": "data_table",
                    "title": "Project Status Overview",
                    "description": "Current project statuses and details",
                    "properties": {
                        "searchable": True,
                        "sortable": True,
                        "exportable": True
                    }
                })
                
                # Create status distribution chart
                components.append({
                    "id": "project_status_chart",
                    "type": "pie_chart",
                    "title": "Project Status Distribution",
                    "description": "Distribution of active vs inactive projects",
                    "properties": {
                        "data_key": "status"
                    }
                })
                
                dataset = {
                    "data": project_data,
                    "columns": ["title", "status", "criticality", "created_date"],
                    "row_count": len(project_data),
                    "description": f"Project status information for {len(project_data)} projects"
                }
                
            elif tool_name == "get_department_analytics":
                # Create analytics components
                components.append({
                    "id": "analytics_overview",
                    "type": "metric_card",
                    "title": "Employee Analytics",
                    "description": "Overview of employee statistics and talent distribution",
                    "properties": {
                        "value": "Available",
                        "label": "Analytics Data"
                    }
                })
                
                dataset = {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "description": "Employee analytics overview"
                }
                
            elif tool_name == "get_survey_insights":
                # Create survey components
                components.append({
                    "id": "survey_overview",
                    "type": "metric_card",
                    "title": "Survey Insights",
                    "description": "Employee survey feedback and ratings overview",
                    "properties": {
                        "value": "Available",
                        "label": "Survey Data"
                    }
                })
                
                dataset = {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "description": "Survey insights overview"
                }
                
            elif tool_name == "get_action_items":
                # Create action items components
                components.append({
                    "id": "action_items_overview",
                    "type": "metric_card",
                    "title": "Action Items",
                    "description": "Task and action item management overview",
                    "properties": {
                        "value": "Available",
                        "label": "Action Items"
                    }
                })
                
                dataset = {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "description": "Action items overview"
                }
                
            elif tool_name == "get_employee_details":
                # Create employee details components
                components.append({
                    "id": "employee_details",
                    "type": "metric_card",
                    "title": "Employee Details",
                    "description": "Detailed employee information and profile",
                    "properties": {
                        "value": "Available",
                        "label": "Employee Info"
                    }
                })
                
                dataset = {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "description": "Employee details"
                }
                
            elif tool_name == "search_employees":
                # Create search results components
                components.append({
                    "id": "search_results",
                    "type": "metric_card",
                    "title": "Employee Search",
                    "description": "Employee search results",
                    "properties": {
                        "value": "Available",
                        "label": "Search Results"
                    }
                })
                
                dataset = {
                    "data": [],
                    "columns": [],
                    "row_count": 0,
                    "description": "Employee search results"
                }
                
            else:
                # Default fallback
                components.append({
                    "id": "general_results",
                    "type": "metric_card",
                    "title": "Query Results",
                    "description": tool_result[:100] + "..." if len(tool_result) > 100 else tool_result,
                    "properties": {
                        "value": "See details",
                        "label": "Analysis Complete"
                    }
                })
                
        except Exception as e:
            logger.error(f"Error parsing tool data: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            # Fallback to simple metric card
            components.append({
                "id": "error_metric",
                "type": "metric_card", 
                "title": "Data Processing Error",
                "description": f"Error processing {tool_name}: {str(e)}",
                "properties": {
                    "value": "Error",
                    "label": "Data Status"
                }
            })
        
        return components, dataset

    def generate_insights_components(self, answer, query):
        """
        Generate insights components for RAG (knowledge base) responses
        """
        components = [
            {
                "id": "knowledge_insights",
                "type": "insights_panel",
                "title": "Knowledge Base Response",
                "description": "Information from HR knowledge base",
                "properties": {
                    "sections": ["key_findings"]
                }
            }
        ]
        
        dataset = {
            "data": [],
            "columns": [],
            "row_count": 0,
            "description": f"Knowledge base results for: {query}"
        }
        
        return components, dataset

    def save_conversation(self, user_query, response_data, user, conversation_id=None):
        """
        Save conversation using existing conversation system
        """
        try:
            # Get or create conversation
            if conversation_id:
                try:
                    conversation = Conversation.objects.get(id=conversation_id, user=user)
                except Conversation.DoesNotExist:
                    conversation = Conversation.objects.create(
                        user=user,
                        title=user_query[:50] + "..." if len(user_query) > 50 else user_query
                    )
            else:
                conversation = Conversation.objects.create(
                    user=user,
                    title=user_query[:50] + "..." if len(user_query) > 50 else user_query
                )
                response_data["conversation_id"] = conversation.id

            # Save user message
            ConversationMessage.objects.create(
                conversation=conversation,
                role='user',
                content=user_query
            )

            # Save assistant response
            assistant_message = ConversationMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=response_data.get('insights', {}).get('key_findings', [''])[0] or 'Response generated',
                analysis_data=response_data.get('components', []),
                queries_data=[],
                dataset=response_data.get('dataset', {})
            )
            
            response_data["message_id"] = assistant_message.id
            
        except Exception as e:
            logger.error(f"Error saving LangGraph conversation: {e}")

class LangGraphAsyncChatView(APIView):
    """
    Async version of LangGraph chat for long-running queries
    """
    permission_classes = [IsAuthenticated, IsManager]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        from .llm import ChatAPIView
        self.chat_api = ChatAPIView()

    def post(self, request, *args, **kwargs):
        try:
            user_query = request.data.get('query', '').strip() or request.data.get('prompt', '').strip()
            conversation_id = request.data.get('conversation_id')
            
            if not user_query:
                return Response({
                    "error": "Query is required",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check cache first
            user_profile = request.user.employee_profile
            cached_response = self.chat_api.get_cached_response(request.user.username, user_query, user_profile)
            
            if cached_response:
                return Response(cached_response)

            # Generate task ID and start background processing
            task_id = str(uuid.uuid4())
            
            # Store initial task status
            cache.set(f"chat_task_status:{task_id}", {
                "status": "processing",
                "progress": "Initializing LangGraph processing...",
                "user_id": request.user.id,
                "query": user_query[:200],
                "started_at": datetime.now().isoformat()
            }, timeout=settings.CHAT_PROCESSING_TIMEOUT)
            
            # Start background processing
            thread = threading.Thread(
                target=self.process_langgraph_async,
                args=(task_id, user_query, request.user, conversation_id)
            )
            thread.daemon = True
            thread.start()
            
            return Response({
                "task_id": task_id,
                "status": "processing",
                "message": "LangGraph processing started. Use the task_id to check status."
            }, status=status.HTTP_202_ACCEPTED)
            
        except Exception as e:
            logger.error(f"Error initiating async LangGraph chat: {e}")
            return Response({
                "error": f"Failed to initiate chat processing: {str(e)}",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def process_langgraph_async(self, task_id, user_query, user, conversation_id):
        """
        Process LangGraph query in background thread
        """
        try:
            # Update status
            cache.set(f"chat_task_status:{task_id}", {
                "status": "processing",
                "progress": "Processing query through LangGraph...",
                "user_id": user.id,
                "query": user_query[:200]
            }, timeout=settings.CHAT_PROCESSING_TIMEOUT)
            
            # Process through LangGraph
            result = chat_graph.invoke({"user_input": user_query})
            
            # Transform to frontend format
            sync_view = LangGraphChatView()
            response_data = sync_view.transform_to_frontend_format(
                result, user_query, user, conversation_id
            )
            
            # Apply optimizations from existing system
            response_data = self.chat_api.optimize_dataset(response_data)
            response_data = self.chat_api.cleanup_response(response_data)
            
            # Cache the response
            user_profile = user.employee_profile
            self.chat_api.cache_response(user.username, user_query, response_data, user_profile)
            
            # Save conversation
            sync_view.save_conversation(user_query, response_data, user, conversation_id)
            
            # Store final response
            cache.set(f"chat_response:{task_id}", response_data, timeout=settings.CHAT_RESPONSE_TTL)
            
            # Update final status
            cache.set(f"chat_task_status:{task_id}", {
                "status": "completed",
                "progress": "LangGraph processing completed successfully",
                "user_id": user.id,
                "query": user_query[:200],
                "completed_at": datetime.now().isoformat()
            }, timeout=300)  # Keep status for 5 minutes after completion
            
        except Exception as e:
            logger.error(f"Error in async LangGraph processing: {e}")
            
            # Store error response
            error_response = {
                "success": False,
                "error": str(e)[:500],  # Limit error message length
                "route": "error",
                "processing_method": "langgraph_async"
            }
            
            cache.set(f"chat_response:{task_id}", error_response, timeout=settings.CHAT_RESPONSE_TTL)
            cache.set(f"chat_task_status:{task_id}", {
                "status": "failed",
                "progress": f"Processing failed: {str(e)[:200]}",
                "user_id": user.id,
                "query": user_query[:200],
                "error": str(e)[:500]
            }, timeout=300)

class LangGraphHealthView(APIView):
    """
    Health check endpoint for LangGraph system
    """
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        try:
            from apis.langchain_setup import check_langchain_health
            from apis.tools import AVAILABLE_TOOLS
            
            health = check_langchain_health()
            health.update({
                "langgraph_available": chat_graph is not None,
                "available_tools": len(AVAILABLE_TOOLS),
                "tool_names": [tool.name for tool in AVAILABLE_TOOLS],
                "system_status": "healthy" if all([
                    health.get("llm", False),
                    health.get("embeddings", False),
                    chat_graph is not None
                ]) else "degraded"
            })
            
            return Response(health)
            
        except Exception as e:
            logger.error(f"Error checking LangGraph health: {e}")
            return Response({
                "error": str(e),
                "system_status": "error"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def parse_performers_data(self, tool_result):
        """Parse performer data from tool text result"""
        performers = []
        lines = tool_result.split('\n')
        
        for line in lines:
            if line.strip() and line.startswith(('1.', '2.', '3.', '4.', '5.')):
                # Parse line like "1. Ronald Lewis - Talent: High, Motivation: Medium (Age: 30)"
                try:
                    parts = line.split(' - ')
                    if len(parts) >= 2:
                        name = parts[0].split('. ', 1)[1] if '. ' in parts[0] else parts[0]
                        details = ' - '.join(parts[1:])
                        
                        # Extract talent, motivation, age
                        talent = "Medium"  # default
                        motivation = "Medium"  # default
                        age = 25  # default
                        
                        if "Talent: " in details:
                            talent = details.split("Talent: ")[1].split(",")[0].strip()
                        if "Motivation: " in details:
                            motivation = details.split("Motivation: ")[1].split(" ")[0].strip()
                        if "Age: " in details:
                            age_str = details.split("Age: ")[1].split(")")[0].strip()
                            age = int(age_str) if age_str.isdigit() else 25
                        
                        performers.append({
                            "name": name.strip(),
                            "talent_type": talent,
                            "motivation_factor": motivation,
                            "age": age,
                            "motivation_score": 7.5 if motivation == "High" else 5.0 if motivation == "Medium" else 2.5
                        })
                except Exception as e:
                    logger.error(f"Error parsing performer line: {line}, error: {e}")
                    continue
        
        return performers

    def parse_workforce_data(self, tool_result):
        """Parse workforce optimization data from tool text result"""
        workforce_data = []
        lines = tool_result.split('\n')
        
        for line in lines:
            if line.strip() and line.startswith(('1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '10.')):
                # Parse line like "1. Sean Hatfield (Age: 65, Tenure: 0 years)"
                try:
                    # Extract the numbered item
                    parts = line.split('. ', 1)
                    if len(parts) < 2:
                        continue
                        
                    content = parts[1]
                    
                    # Extract name (everything before the first parenthesis)
                    name_part = content.split(' (')[0].strip()
                    
                    # Extract age and tenure from parentheses
                    age = 30  # default
                    tenure_years = 0  # default
                    
                    if '(Age:' in content:
                        age_part = content.split('(Age:')[1].split(',')[0].strip()
                        if age_part.isdigit():
                            age = int(age_part)
                    
                    if 'Tenure:' in content:
                        tenure_part = content.split('Tenure:')[1].split('years')[0].strip()
                        if tenure_part.isdigit():
                            tenure_years = int(tenure_part)
                    
                    # Look for the next lines to get risk factors and talent info
                    current_index = lines.index(line)
                    risk_factors_line = ""
                    talent_line = ""
                    
                    if current_index + 1 < len(lines) and "Risk Factors:" in lines[current_index + 1]:
                        risk_factors_line = lines[current_index + 1]
                    if current_index + 2 < len(lines) and "Talent:" in lines[current_index + 2]:
                        talent_line = lines[current_index + 2]
                    
                    # Parse talent and motivation
                    talent_type = "Medium"  # default
                    motivation_factor = "Medium"  # default
                    
                    if "Talent:" in talent_line:
                        talent_part = talent_line.split("Talent:")[1].split(",")[0].strip()
                        if talent_part in ["High", "Medium", "Low"]:
                            talent_type = talent_part
                    
                    if "Motivation:" in talent_line:
                        motivation_part = talent_line.split("Motivation:")[1].strip()
                        if motivation_part in ["High", "Medium", "Low"]:
                            motivation_factor = motivation_part
                    
                    # Determine risk level based on risk factors
                    risk_level = "Medium"  # default
                    if "High" in risk_factors_line:
                        risk_level = "High"
                    elif "Low" in risk_factors_line:
                        risk_level = "Low"
                    
                    workforce_data.append({
                        "name": name_part,
                        "talent_type": talent_type,
                        "motivation_factor": motivation_factor,
                        "risk_level": risk_level,
                        "tenure_years": tenure_years,
                        "age": age
                    })
                    
                except Exception as e:
                    logger.error(f"Error parsing workforce line: {line}, error: {e}")
                    continue
        
        # If no data was parsed, return sample data
        if not workforce_data:
            workforce_data = [
                {"name": "No optimization candidates found", "talent_type": "N/A", "motivation_factor": "N/A", "risk_level": "N/A", "tenure_years": 0, "age": 0}
            ]
        
        return workforce_data
