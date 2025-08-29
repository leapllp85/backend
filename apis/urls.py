from django.urls import path
from .views.projects import ProjectAPIView, MyProjectsAPIView, TeamProjectsAPIView
from .views.courses import CourseAPIView
from .views.actionitems import ActionItemAPIView
from .views.llm import ChatAPIView

from .views.team import MyTeamAPIView, TeamAnalyticsAPIView, AttritionGraphAPIView, DistributionGraphAPIView
from .views.dashboard import DashboardQuickDataAPIView, TeamAttritionRiskAPIView, TeamMentalHealthAPIView, TeamUtilizationAPIView
from .views.allocations import ProjectAllocationAPIView, ProjectTeamAPIView, EmployeeAllocationSummaryAPIView
from .views.surveys import SurveyListAPIView, SurveyDetailAPIView, SurveyResponseAPIView, SurveyManagementAPIView, MySurveyResponsesAPIView, ManagerSurveyPublishAPIView

urlpatterns = [
    # Projects - Role-based access controlled in views
    path('projects/', ProjectAPIView.as_view(), name='projects'),
    path('my-projects/', MyProjectsAPIView.as_view(), name='my-projects'),
    path('team-projects/', TeamProjectsAPIView.as_view(), name='team-projects'),
    
    # Core functionality - Available to authenticated users
    path('courses/', CourseAPIView.as_view(), name='courses'),
    path('action-items/', ActionItemAPIView.as_view(), name='action-items'),
    path('chat/', ChatAPIView.as_view(), name='llm-chat'),
    
    # Team Management - Access controlled by permissions
    path('my-team/', MyTeamAPIView.as_view(), name='my-team'),
    path('team-analytics/', TeamAnalyticsAPIView.as_view(), name='team-analytics'),
    path('team-analytics/attrition-graph/', AttritionGraphAPIView.as_view(), name='team-attrition-graph'),
    path('team-analytics/distribution-graph/', DistributionGraphAPIView.as_view(), name='team-distribution-graph'),
    
    # Dashboard - Access controlled by permissions
    path('dashboard/quick-data/', DashboardQuickDataAPIView.as_view(), name='dashboard-quick-data'),
    path('dashboard/attrition-risk/', TeamAttritionRiskAPIView.as_view(), name='dashboard-attrition-risk'),
    path('dashboard/mental-health/', TeamMentalHealthAPIView.as_view(), name='dashboard-mental-health'),
    path('dashboard/utilization/', TeamUtilizationAPIView.as_view(), name='dashboard-utilization'),
    
    # Project Allocations - Access controlled by permissions
    path('allocations/', ProjectAllocationAPIView.as_view(), name='project-allocations'),
    path('project-team/<int:project_id>/', ProjectTeamAPIView.as_view(), name='project-team'),
    path('employee-allocation-summary/', EmployeeAllocationSummaryAPIView.as_view(), name='employee-allocation-summary'),
    
    # Surveys - Role-based access controlled in views
    path('surveys/', SurveyListAPIView.as_view(), name='surveys'),
    path('surveys/<int:survey_id>/', SurveyDetailAPIView.as_view(), name='survey-detail'),
    path('surveys/<int:survey_id>/respond/', SurveyResponseAPIView.as_view(), name='survey-response'),
    path('my-survey-responses/', MySurveyResponsesAPIView.as_view(), name='my-survey-responses'),
    path('survey-management/', SurveyManagementAPIView.as_view(), name='survey-management'),
    path('manager/publish-survey/', ManagerSurveyPublishAPIView.as_view(), name='manager-publish-survey'),
]
