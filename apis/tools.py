"""
Django ORM Tools for MCP (Model Context Protocol)
Provides structured data access tools for LangChain agents
"""
import logging
from typing import Dict, List, Optional, Any
from django.db.models import Count, Avg, Q, Max, Min, Sum
from django.db import models
from langchain.tools import tool
from datetime import datetime, timedelta

# Import your existing models
from .models import (
    EmployeeProfile, Project, Course, Survey, ActionItem, 
    ProjectAllocation, SurveyResponse, Attrition
)

logger = logging.getLogger(__name__)

@tool("get_best_performers", return_direct=True)
def get_best_performers(limit: str = "5") -> str:
    """Find top performing employees based on talent type and motivation factors"""
    try:
        limit_int = int(limit) if limit.isdigit() else 5
        
        performers = (
            EmployeeProfile.objects
            .select_related('user')
            .filter(talent_type__isnull=False)
            .order_by('-talent_type', '-motivation_factor')
            .values('user__username', 'user__first_name', 'user__last_name', 
                   'talent_type', 'motivation_factor', 'age')[:limit_int]
        )
        
        if not performers:
            return "No employee performance data available."
        
        result = "Top Performers:\n"
        for i, emp in enumerate(performers, 1):
            name = f"{emp['user__first_name']} {emp['user__last_name']}" if emp['user__first_name'] else emp['user__username']
            result += f"{i}. {name} - Talent: {emp['talent_type']}, Motivation: {emp['motivation_factor']}, Age: {emp['age']}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting best performers: {e}")
        return f"Error retrieving performance data: {str(e)}"

@tool("get_attrition_risk", return_direct=True)
def get_attrition_risk() -> str:
    """Analyze employee attrition risk levels across the organization"""
    try:
        # Get attrition risk data
        risk_data = Attrition.objects.aggregate(
            high_risk=Count('id', filter=Q(high=True)),
            medium_risk=Count('id', filter=Q(medium=True)),
            low_risk=Count('id', filter=Q(low=True)),
            total=Count('id')
        )
        
        # Get employee risk assessment data
        employee_risks = (
            EmployeeProfile.objects
            .values('manager_assessment_risk')
            .annotate(count=Count('id'))
            .order_by('manager_assessment_risk')
        )
        
        result = f"Attrition Risk Analysis:\n"
        result += f"• High Risk: {risk_data['high_risk']} employees\n"
        result += f"• Medium Risk: {risk_data['medium_risk']} employees\n"
        result += f"• Low Risk: {risk_data['low_risk']} employees\n"
        result += f"• Total Assessed: {risk_data['total']} employees\n\n"
        
        if employee_risks:
            result += "Manager Risk Assessments:\n"
            for risk in employee_risks:
                if risk['manager_assessment_risk']:
                    result += f"• {risk['manager_assessment_risk']}: {risk['count']} employees\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting attrition risk: {e}")

@tool("get_project_status", return_direct=True)
def get_project_status() -> str:
    """Get current project status and allocation information"""
    try:
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
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting project status: {e}")
        return f"Error retrieving project data: {str(e)}"

@tool("get_survey_insights", return_direct=True)
def get_survey_insights(query: str = "") -> str:
    """Get insights from recent employee surveys and feedback"""
    try:
        # Survey summary
        survey_stats = Survey.objects.aggregate(
            total=Count('id'),
            recent=Count('id', filter=Q(created_at__gte=datetime.now() - timedelta(days=30)))
        )
        
        # Recent surveys
        recent_surveys = (
            Survey.objects
            .order_by('-created_at')
            .values('survey_name', 'survey_type', 'created_at')[:5]
        )
        
        # Survey responses if available
        response_stats = SurveyResponse.objects.aggregate(
            total_responses=Count('id'),
            avg_rating=Avg('rating')
        )
        
        result = f"Survey Insights:\n"
        result += f"• Total Surveys: {survey_stats['total']}\n"
        result += f"• Recent Surveys (30 days): {survey_stats['recent']}\n"
        result += f"• Total Responses: {response_stats['total_responses']}\n"
        result += f"• Average Rating: {response_stats['avg_rating']:.2f}\n\n" if response_stats['avg_rating'] else "• Average Rating: N/A\n\n"
        
        if recent_surveys:
            result += "Recent Surveys:\n"
            for survey in recent_surveys:
                result += f"• {survey['survey_name']} ({survey['survey_type']}) - {survey['created_at'].strftime('%Y-%m-%d')}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting survey insights: {e}")
        return f"Error retrieving survey data: {str(e)}"

@tool("get_action_items", return_direct=True)
def get_action_items(status: str = "all") -> str:
    """Get action items and tasks, optionally filtered by status"""
    try:
        queryset = ActionItem.objects.all()
        
        if status.lower() != "all":
            queryset = queryset.filter(status__icontains=status)
        
        # Action item summary
        action_stats = queryset.aggregate(
            total=Count('id'),
            high_priority=Count('id', filter=Q(priority='HIGH')),
            medium_priority=Count('id', filter=Q(priority='MEDIUM')),
            low_priority=Count('id', filter=Q(priority='LOW'))
        )
        
        # Recent action items
        recent_actions = (
            queryset
            .order_by('-created_at')
            .values('title', 'priority', 'status', 'due_date', 'created_at')[:10]
        )
        
        result = f"Action Items Overview:\n"
        result += f"• Total Items: {action_stats['total']}\n"
        result += f"• High Priority: {action_stats['high_priority']}\n"
        result += f"• Medium Priority: {action_stats['medium_priority']}\n"
        result += f"• Low Priority: {action_stats['low_priority']}\n\n"
        
        if recent_actions:
            result += "Recent Action Items:\n"
            for action in recent_actions:
                due_date = action['due_date'].strftime('%Y-%m-%d') if action['due_date'] else 'No due date'
                result += f"• {action['title']} - {action['priority']} priority ({action['status']}) - Due: {due_date}\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting action items: {e}")
        return f"Error retrieving action items: {str(e)}"

@tool("get_employee_details", return_direct=True)
def get_employee_details(username: str) -> str:
    """Get detailed information about a specific employee"""
    try:
        employee = (
            EmployeeProfile.objects
            .select_related('user')
            .filter(Q(user__username__icontains=username) | 
                   Q(user__first_name__icontains=username) |
                   Q(user__last_name__icontains=username))
            .first()
        )
        
        if not employee:
            return f"Employee '{username}' not found."
        
        result = f"Employee Details: {employee.user.first_name} {employee.user.last_name}\n"
        result += f"• Username: {employee.user.username}\n"
        result += f"• Email: {employee.user.email}\n"
        result += f"• Department: {employee.department}\n"
        result += f"• Role: {employee.role}\n"
        result += f"• Manager: {'Yes' if employee.is_manager else 'No'}\n"
        result += f"• Motivation Factor: {employee.motivation_factor}\n"
        result += f"• Performance Score: {employee.performance_score}\n" if hasattr(employee, 'performance_score') else ""
        result += f"• Risk Assessment: {employee.manager_assessment_risk}\n"
        result += f"• Joined: {employee.user.date_joined.strftime('%Y-%m-%d')}\n"
        
        # Get project allocations
        allocations = ProjectAllocation.objects.filter(employee_id=employee.user.id).select_related('project')
        if allocations:
            result += f"\nProject Allocations:\n"
            for alloc in allocations:
                result += f"• {alloc.project.project_name} - {alloc.allocation_percentage}% allocation\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting employee details: {e}")
        return f"Error retrieving employee details: {str(e)}"

@tool("get_department_analytics", return_direct=True)
def get_department_analytics(department: str = "") -> str:
    """Get analytics for employee talent types and motivation levels"""
    try:
        queryset = EmployeeProfile.objects.all()
        title = "Employee Analytics Overview"
        
        # Employee statistics
        emp_stats = queryset.aggregate(
            total_employees=Count('id'),
            avg_motivation=Avg('motivation_factor'),
            managers=Count('id', filter=Q(manager__isnull=False)),
            high_talent=Count('id', filter=Q(talent_type='High'))
        )
        
        # Talent type breakdown
        talent_breakdown = (
            EmployeeProfile.objects
            .values('talent_type')
            .annotate(
                count=Count('id'),
                avg_motivation=Avg('motivation_factor')
            )
            .order_by('-count')
        )
        
        result = f"{title}:\n"
        result += f"• Total Employees: {emp_stats['total_employees']}\n"
        result += f"• Average Motivation: {emp_stats['avg_motivation']:.2f}\n" if emp_stats['avg_motivation'] else "• Average Motivation: N/A\n"
        result += f"• Managers: {emp_stats['managers']}\n"
        result += f"• High Talent: {emp_stats['high_talent']}\n\n"
        
        if talent_breakdown:
            result += "Talent Type Breakdown:\n"
            for talent in talent_breakdown:
                if talent['talent_type']:
                    avg_mot = f"{talent['avg_motivation']:.2f}" if talent['avg_motivation'] else "N/A"
                    result += f"• {talent['talent_type']}: {talent['count']} employees (Avg motivation: {avg_mot})\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting department analytics: {e}")
        return f"Error retrieving department data: {str(e)}"

@tool("search_employees", return_direct=True)
def search_employees(query: str = "", limit: str = "10") -> str:
    """Search for employees by name or talent type"""
    try:
        limit_int = int(limit) if limit.isdigit() else 10
        
        employees = (
            EmployeeProfile.objects
            .select_related('user')
            .filter(
                Q(user__username__icontains=query) |
                Q(user__first_name__icontains=query) |
                Q(user__last_name__icontains=query) |
                Q(talent_type__icontains=query)
            )
            .values('user__username', 'user__first_name', 'user__last_name',
                   'talent_type', 'motivation_factor', 'age')[:limit_int]
        )
        
        if not employees:
            return f"No employees found matching '{query}'."
        
        result = f"Search Results for '{query}':\n"
        for emp in employees:
            name = f"{emp['user__first_name']} {emp['user__last_name']}" if emp['user__first_name'] else emp['user__username']
            talent = f" - Talent: {emp['talent_type']}" if emp['talent_type'] else ""
            motivation = f" - Motivation: {emp['motivation_factor']}" if emp['motivation_factor'] else ""
            result += f"• {name}{talent}{motivation} (Age: {emp['age']})\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error searching employees: {e}")
        return f"Error searching employees: {str(e)}"

@tool("get_workforce_optimization", return_direct=True)
def get_workforce_optimization() -> str:
    """Analyze workforce for optimization opportunities based on performance, risk, and criticality"""
    try:
        # Get employees with low performance indicators
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
            return "No employees identified for workforce optimization based on current performance metrics."
        
        result = "Workforce Optimization Analysis:\n\n"
        result += "Employees with optimization opportunities (based on performance metrics):\n"
        
        for i, emp in enumerate(low_performers, 1):
            name = f"{emp['user__first_name']} {emp['user__last_name']}" if emp['user__first_name'] else emp['user__username']
            
            # Risk indicators
            risk_factors = []
            if emp['talent_type'] == 'Low':
                risk_factors.append("Low Talent")
            if emp['motivation_factor'] == 'Low':
                risk_factors.append("Low Motivation")
            if emp['manager_assessment_risk'] == 'High':
                risk_factors.append("High Manager Risk Assessment")
            if emp['suggested_risk'] == 'High':
                risk_factors.append("High System Risk Assessment")
            
            tenure_years = (datetime.now().date() - emp['created_at'].date()).days // 365 if emp['created_at'] else 0
            
            result += f"{i}. {name} (Age: {emp['age']}, Tenure: {tenure_years} years)\n"
            result += f"   Risk Factors: {', '.join(risk_factors)}\n"
            result += f"   Talent: {emp['talent_type']}, Motivation: {emp['motivation_factor']}\n\n"
        
        # Summary statistics
        total_employees = EmployeeProfile.objects.count()
        optimization_candidates = len(low_performers)
        
        result += f"Summary:\n"
        result += f"• Total Employees: {total_employees}\n"
        result += f"• Optimization Candidates: {optimization_candidates}\n"
        result += f"• Percentage: {(optimization_candidates/total_employees)*100:.1f}%\n\n"
        
        result += "Note: This analysis is based on performance metrics, risk assessments, and talent evaluations. "
        result += "Consider additional factors like project criticality, skills, and business needs before making decisions."
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting workforce optimization: {e}")
        return f"Error retrieving workforce optimization data: {str(e)}"

# Tool registry for easy access
AVAILABLE_TOOLS = [
    get_best_performers,
    get_attrition_risk,
    get_project_status,
    get_survey_insights,
    get_action_items,
    get_employee_details,
    get_department_analytics,
    search_employees,
    get_workforce_optimization
]

def get_tool_descriptions() -> Dict[str, str]:
    """Get descriptions of all available tools"""
    return {tool.name: tool.description for tool in AVAILABLE_TOOLS}
