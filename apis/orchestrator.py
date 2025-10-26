"""
Simplified LangGraph Orchestrator for HR Conversational Analytics
Routes queries between MCP (structured data), RAG (knowledge base), and Escalation nodes
"""
import logging
from typing import TypedDict, Literal, Optional, Dict, Any
from langchain.agents import initialize_agent, AgentType, Tool
from langchain.prompts import PromptTemplate
from langgraph.graph import StateGraph, END
from .tools import AVAILABLE_TOOLS
from .langchain_setup import (
    llm, rag_chain, mcp_chain, escalation_chain, 
    fallback_similarity_search, get_similar_documents
)

logger = logging.getLogger(__name__)

def classify_query(user_input: str) -> str:
    """
    Classify user query to determine routing
    """
    query_lower = user_input.lower()
    
    # MCP keywords for structured data queries
    mcp_keywords = [
        'performance', 'best', 'top', 'worst', 'ranking', 'analytics', 
        'metrics', 'data', 'statistics', 'numbers', 'count', 'list',
        'project', 'status', 'survey', 'feedback', 'risk', 'attrition',
        'department', 'team', 'employee', 'staff', 'talent', 'layoff',
        'fire', 'terminate', 'remove', 'optimize', 'reduce', 'downsize',
        'underperform', 'low', 'poor', 'weak', 'assessment', 'criticality'
    ]
    
    # Check for MCP keywords
    if any(keyword in query_lower for keyword in mcp_keywords):
        return "mcp"
    
    # Default to RAG for general queries, policies, procedures
    return "rag"

class ChatState(TypedDict):
    user_input: str
    route: str
    answer: str
    tool_data: Optional[Dict[str, Any]]

def router_node(state: ChatState):
    route = classify_query(state["user_input"])
    state["route"] = route
    return state

def mcp_node(state: ChatState):
    if not llm:
        state["answer"] = "I can help you with HR data queries, but the AI system is not fully available. Please ensure the ANTHROPIC_API_KEY is configured."
        return state
    
    # Direct tool execution based on query keywords for better data extraction
    query = state["user_input"].lower()
    
    try:
        # Check workforce optimization keywords first (higher priority)
        if any(keyword in query for keyword in ['layoff', 'fire', 'terminate', 'remove', 'optimize', 'reduce', 'downsize', 'underperform', 'low', 'poor', 'weak']):
            # Import and call the function directly
            from apis.tools import get_workforce_optimization
            # Call the underlying function directly
            import inspect
            if hasattr(get_workforce_optimization, 'func'):
                tool_result = get_workforce_optimization.func()
            else:
                # Fallback: call the function by name
                from apis.tools import EmployeeProfile
                from django.db.models import Q
                from datetime import datetime
                
                # Inline workforce optimization logic
                try:
                    low_performers = (
                        EmployeeProfile.objects
                        .select_related('user')
                        .filter(
                            Q(talent_type='Low') | 
                            Q(motivation_factor='Low') |
                            Q(manager_assessment_risk='High') |
                            Q(suggested_risk='High')
                        )
                        .order_by('talent_type', 'motivation_factor', '-manager_assessment_risk')
                        .values('user__username', 'user__first_name', 'user__last_name',
                               'talent_type', 'motivation_factor', 'manager_assessment_risk', 
                               'suggested_risk', 'age', 'created_at')[:10]
                    )
                    
                    if not low_performers:
                        tool_result = "No employees identified for workforce optimization based on current performance metrics."
                    else:
                        result = "Workforce Optimization Analysis:\n\n"
                        result += "Employees with optimization opportunities (based on performance metrics):\n"
                        
                        for i, emp in enumerate(low_performers, 1):
                            name = f"{emp['user__first_name']} {emp['user__last_name']}" if emp['user__first_name'] else emp['user__username']
                            result += f"{i}. {name} - Talent: {emp['talent_type']}, Motivation: {emp['motivation_factor']}, Risk: {emp['manager_assessment_risk']}\n"
                        
                        tool_result = result
                except Exception as e:
                    tool_result = f"Error analyzing workforce: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_workforce_optimization",
                "result": tool_result,
                "query_type": "workforce_optimization"
            }
        elif any(keyword in query for keyword in ['best', 'top', 'performer']) and not any(keyword in query for keyword in ['terminate', 'layoff', 'fire', 'remove']):
            # Only match performance keywords if no workforce optimization keywords are present
            from .tools import get_best_performers
            tool_result = get_best_performers("5")
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_best_performers",
                "result": tool_result,
                "query_type": "performance"
            }
        elif any(keyword in query for keyword in ['risk', 'attrition']):
            # Call attrition risk function directly
            try:
                from apis.tools import EmployeeProfile
                from django.db.models import Count, Q
                
                # Attrition risk analysis
                risk_stats = EmployeeProfile.objects.aggregate(
                    total=Count('id'),
                    high_risk=Count('id', filter=Q(manager_assessment_risk='High')),
                    medium_risk=Count('id', filter=Q(manager_assessment_risk='Medium')),
                    low_risk=Count('id', filter=Q(manager_assessment_risk='Low'))
                )
                
                # Get high-risk employees
                high_risk_employees = (
                    EmployeeProfile.objects
                    .select_related('user')
                    .filter(manager_assessment_risk='High')
                    .values('user__username', 'user__first_name', 'user__last_name',
                           'talent_type', 'motivation_factor', 'age')[:10]
                )
                
                result = "Attrition Risk Analysis:\n\n"
                result += f"Risk Distribution:\n"
                result += f"• High Risk: {risk_stats['high_risk']} employees\n"
                result += f"• Medium Risk: {risk_stats['medium_risk']} employees\n"
                result += f"• Low Risk: {risk_stats['low_risk']} employees\n\n"
                
                if high_risk_employees:
                    result += "High Risk Employees:\n"
                    for i, emp in enumerate(high_risk_employees, 1):
                        name = f"{emp['user__first_name']} {emp['user__last_name']}" if emp['user__first_name'] else emp['user__username']
                        result += f"{i}. {name} - Talent: {emp['talent_type']}, Motivation: {emp['motivation_factor']}, Age: {emp['age']}\n"
                else:
                    result += "No high-risk employees identified."
                
                tool_result = result
                
            except Exception as e:
                tool_result = f"Error analyzing attrition risk: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_attrition_risk", 
                "result": tool_result,
                "query_type": "risk"
            }
        elif any(keyword in query for keyword in ['project', 'status']):
            # Call project status function directly
            try:
                from apis.tools import Project
                from django.db.models import Count, Q
                
                # Project statistics (using correct field names from Project model)
                project_stats = Project.objects.aggregate(
                    total=Count('id'),
                    active=Count('id', filter=Q(status='Active')),
                    inactive=Count('id', filter=Q(status='Inactive'))
                )
                
                # Recent projects
                recent_projects = (
                    Project.objects
                    .order_by('-created_at')
                    .values('title', 'status', 'criticality', 'created_at')[:5]
                )
                
                result = f"Project Status Overview:\n"
                result += f"• Total Projects: {project_stats['total']}\n"
                result += f"• Active: {project_stats['active']}\n"
                result += f"• Inactive: {project_stats['inactive']}\n\n"
                
                if recent_projects:
                    result += "Recent Projects:\n"
                    for proj in recent_projects:
                        result += f"• {proj['title']} - {proj['status']} (Criticality: {proj['criticality']})\n"
                
                tool_result = result
                
            except Exception as e:
                tool_result = f"Error analyzing projects: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_project_status",
                "result": tool_result,
                "query_type": "projects"
            }
        elif any(keyword in query for keyword in ['department', 'analytics', 'talent']):
            # Call department analytics function directly
            try:
                from apis.tools import EmployeeProfile
                from django.db.models import Count, Avg, Q
                
                # Employee statistics
                emp_stats = EmployeeProfile.objects.aggregate(
                    total_employees=Count('id'),
                    managers=Count('id', filter=Q(manager__isnull=False)),
                    high_talent=Count('id', filter=Q(talent_type='High'))
                )
                
                # Talent type breakdown
                talent_breakdown = (
                    EmployeeProfile.objects
                    .values('talent_type')
                    .annotate(count=Count('id'))
                    .order_by('-count')
                )
                
                result = "Employee Analytics Overview:\n"
                result += f"• Total Employees: {emp_stats['total_employees']}\n"
                result += f"• Managers: {emp_stats['managers']}\n"
                result += f"• High Talent: {emp_stats['high_talent']}\n\n"
                
                if talent_breakdown:
                    result += "Talent Type Breakdown:\n"
                    for talent in talent_breakdown:
                        if talent['talent_type']:
                            result += f"• {talent['talent_type']}: {talent['count']} employees\n"
                
                tool_result = result
                
            except Exception as e:
                tool_result = f"Error analyzing department analytics: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_department_analytics",
                "result": tool_result,
                "query_type": "analytics"
            }
        elif any(keyword in query for keyword in ['survey', 'feedback', 'insights']):
            # Call survey insights function directly
            try:
                from apis.tools import Survey
                from django.db.models import Count, Avg, Q
                
                # Survey statistics
                survey_stats = Survey.objects.aggregate(
                    total_surveys=Count('id'),
                    anonymous_surveys=Count('id', filter=Q(is_anonymous=True))
                )
                
                # Recent surveys
                recent_surveys = (
                    Survey.objects
                    .order_by('-created_at')
                    .values('title', 'survey_type', 'is_anonymous', 'created_at')[:5]
                )
                
                result = "Survey Insights Overview:\n"
                result += f"• Total Surveys: {survey_stats['total_surveys']}\n"
                result += f"• Anonymous Surveys: {survey_stats['anonymous_surveys']}\n\n"
                
                if recent_surveys:
                    result += "Recent Surveys:\n"
                    for survey in recent_surveys:
                        anon_str = "Anonymous" if survey['is_anonymous'] else "Named"
                        result += f"• {survey['title']} ({survey['survey_type']}) - {anon_str}\n"
                
                tool_result = result
                
            except Exception as e:
                tool_result = f"Error analyzing survey insights: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_survey_insights",
                "result": tool_result,
                "query_type": "surveys"
            }
        elif any(keyword in query for keyword in ['action items', 'tasks', 'todo']) or ('action' in query and 'items' in query):
            # Call action items function directly
            try:
                from apis.tools import ActionItem
                from django.db.models import Count, Q
                
                # Action item statistics
                action_stats = ActionItem.objects.aggregate(
                    total_items=Count('id'),
                    pending=Count('id', filter=Q(status='Pending')),
                    completed=Count('id', filter=Q(status='Completed')),
                    high_priority=Count('id', filter=Q(priority='High'))
                )
                
                # Recent action items
                recent_actions = (
                    ActionItem.objects
                    .order_by('-created_at')
                    .values('title', 'priority', 'status', 'due_date')[:5]
                )
                
                result = "Action Items Overview:\n"
                result += f"• Total Action Items: {action_stats['total_items']}\n"
                result += f"• Pending: {action_stats['pending']}\n"
                result += f"• Completed: {action_stats['completed']}\n"
                result += f"• High Priority: {action_stats['high_priority']}\n\n"
                
                if recent_actions:
                    result += "Recent Action Items:\n"
                    for action in recent_actions:
                        due_date = action['due_date'].strftime('%Y-%m-%d') if action['due_date'] else 'No due date'
                        result += f"• {action['title']} - {action['priority']} priority ({action['status']}) - Due: {due_date}\n"
                
                tool_result = result
                
            except Exception as e:
                tool_result = f"Error analyzing action items: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_action_items",
                "result": tool_result,
                "query_type": "action_items"
            }
        elif any(keyword in query for keyword in ['employee details', 'employee info', 'staff details']):
            # Call employee details function directly - requires username parameter
            try:
                # Extract potential username from query
                words = query.split()
                username = ""
                for word in words:
                    if len(word) > 3 and word not in ['employee', 'details', 'info', 'staff', 'about', 'show', 'get']:
                        username = word
                        break
                
                if not username:
                    tool_result = "Please specify an employee username or name to get details."
                else:
                    from apis.tools import EmployeeProfile
                    from django.db.models import Q
                    
                    employee = (
                        EmployeeProfile.objects
                        .select_related('user')
                        .filter(Q(user__username__icontains=username) | 
                               Q(user__first_name__icontains=username) |
                               Q(user__last_name__icontains=username))
                        .first()
                    )
                    
                    if not employee:
                        tool_result = f"Employee '{username}' not found."
                    else:
                        result = f"Employee Details: {employee.user.first_name} {employee.user.last_name}\n"
                        result += f"• Username: {employee.user.username}\n"
                        result += f"• Email: {employee.user.email}\n"
                        result += f"• Talent Type: {employee.talent_type}\n"
                        result += f"• Motivation Factor: {employee.motivation_factor}\n"
                        result += f"• Age: {employee.age}\n"
                        result += f"• Manager Assessment Risk: {employee.manager_assessment_risk}\n"
                        
                        tool_result = result
                
            except Exception as e:
                tool_result = f"Error getting employee details: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "get_employee_details",
                "result": tool_result,
                "query_type": "employee_details"
            }
        elif any(keyword in query for keyword in ['search', 'find', 'lookup']):
            # Call search employees function directly
            try:
                from apis.tools import EmployeeProfile
                from django.db.models import Q
                
                # Extract search term from query
                search_terms = query.replace('search', '').replace('find', '').replace('lookup', '').replace('employees', '').strip()
                
                if not search_terms:
                    tool_result = "Please specify search terms to find employees."
                else:
                    employees = (
                        EmployeeProfile.objects
                        .select_related('user')
                        .filter(
                            Q(user__username__icontains=search_terms) |
                            Q(user__first_name__icontains=search_terms) |
                            Q(user__last_name__icontains=search_terms) |
                            Q(talent_type__icontains=search_terms)
                        )
                        .values('user__username', 'user__first_name', 'user__last_name',
                               'talent_type', 'motivation_factor', 'age')[:10]
                    )
                    
                    if not employees:
                        tool_result = f"No employees found matching '{search_terms}'."
                    else:
                        result = f"Search Results for '{search_terms}':\n"
                        for emp in employees:
                            name = f"{emp['user__first_name']} {emp['user__last_name']}" if emp['user__first_name'] else emp['user__username']
                            talent = f" - Talent: {emp['talent_type']}" if emp['talent_type'] else ""
                            motivation = f" - Motivation: {emp['motivation_factor']}" if emp['motivation_factor'] else ""
                            result += f"• {name}{talent}{motivation} (Age: {emp['age']})\n"
                        
                        tool_result = result
                
            except Exception as e:
                tool_result = f"Error searching employees: {str(e)}"
            
            state["answer"] = tool_result
            state["tool_data"] = {
                "tool": "search_employees",
                "result": tool_result,
                "query_type": "search"
            }
        else:
            # Fallback to agent for complex queries
            tools = [
                Tool(name=tool.name, func=tool.func, description=tool.description)
                for tool in AVAILABLE_TOOLS
            ]
            agent = initialize_agent(tools, llm, agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION)
            answer = agent.run(state["user_input"])
            state["answer"] = answer
            state["tool_data"] = {
                "tool": "agent",
                "result": answer,
                "query_type": "general"
            }
    except Exception as e:
        logger.error(f"Error in MCP node: {e}")
        state["answer"] = f"Error processing query: {str(e)}"
        state["tool_data"] = {
            "tool": "error",
            "result": f"Error: {str(e)}",
            "query_type": "error"
        }
    
    return state

def rag_node(state: ChatState):
    docs = get_similar_documents(state["user_input"], k=3)
    context = "\n\n".join([d.page_content for d in docs])
    if rag_chain:
        answer = rag_chain.invoke({"context": context, "question": state["user_input"]})
    else:
        answer = f"Based on the available information: {context[:200]}... I can help you with HR-related questions, but the full AI system is not available right now."
    state["answer"] = answer
    return state

# Build the simplified LangGraph
graph = StateGraph(ChatState)
graph.add_node("router", router_node)
graph.add_node("mcp", mcp_node)
graph.add_node("rag", rag_node)
graph.set_entry_point("router")
graph.add_conditional_edges("router", lambda s: s["route"], {"mcp": "mcp", "rag": "rag"})
graph.add_edge("mcp", END)
graph.add_edge("rag", END)
chat_graph = graph.compile()

