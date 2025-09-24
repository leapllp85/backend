from django.urls import path, include
from .views.projects import ProjectAPIView, MyProjectsAPIView, TeamProjectsAPIView
from .views.courses import CourseAPIView
from .views.actionitems import ActionItemAPIView
from .views.llm import ChatAPIView
from .views.chat_async import ChatInitiateView, ChatResponseView, ChatStatusView

from .views.team import MyTeamAPIView, TeamAnalyticsAPIView, AttritionGraphAPIView, DistributionGraphAPIView, TeamStatsAPIView, ProjectStatsAPIView, MetricsAPIView, NotificationsAPIView, ProjectRisksAPIView
from .views.dashboard import DashboardQuickDataAPIView, TeamAttritionRiskAPIView, TeamMentalHealthAPIView, TeamUtilizationAPIView
from .views.allocations import ProjectAllocationAPIView, ProjectTeamAPIView, EmployeeAllocationSummaryAPIView
from .views.users import UserSearchAPIView
from .views.surveys import SurveyListAPIView, SurveyDetailAPIView, SurveyResponseAPIView, SurveyManagementAPIView, MySurveyResponsesAPIView, ManagerSurveyPublishAPIView
from .views.conversations import (
    ConversationListCreateView, ConversationDetailView, ConversationMessageListView,
    ConversationShareListCreateView, add_message_to_conversation,
    remove_conversation_share, get_shared_conversations
)
from .views.criticality import CriticalityVsRiskView, RiskDistributionView, CriticalityMetricsAPIView, CriticalityTrendsAPIView

urlpatterns = [
    # Projects - Role-based access controlled in views
    path('projects/', ProjectAPIView.as_view(), name='projects'),
    path('my-projects/', MyProjectsAPIView.as_view(), name='my-projects'),
    path('team-projects/', TeamProjectsAPIView.as_view(), name='team-projects'),
    
    # Core functionality - Available to authenticated users
    path('courses/', CourseAPIView.as_view(), name='courses'),
    path('action-items/', ActionItemAPIView.as_view(), name='action-items'),
    path('chat/', ChatAPIView.as_view(), name='llm-chat'),  # Legacy sync chat endpoint
    
    # Async Chat System - Manager only
    path('chat/initiate/', ChatInitiateView.as_view(), name='chat-initiate'),
    path('chat/response/<str:task_id>/', ChatResponseView.as_view(), name='chat-response'),
    path('chat/status/', ChatStatusView.as_view(), name='chat-status'),
    
    # Team Management - Access controlled by permissions
    path('my-team/', MyTeamAPIView.as_view(), name='my-team'),
    path('my-team/<int:employee_id>/', MyTeamAPIView.as_view(), name='my-team-detail'),
    path('team-analytics/', TeamAnalyticsAPIView.as_view(), name='team-analytics'),
    path('team-stats/', TeamStatsAPIView.as_view(), name='team-stats'),
    path('project-stats/', ProjectStatsAPIView.as_view(), name='project-stats'),
    path('metrics/', MetricsAPIView.as_view(), name='metrics'),
    path('notifications/', NotificationsAPIView.as_view(), name='notifications'),
    path('project-risks/', ProjectRisksAPIView.as_view(), name='project-risks'),
    path('team-analytics/attrition-graph/', AttritionGraphAPIView.as_view(), name='team-attrition-graph'),
    path('team-analytics/distribution-graph/', DistributionGraphAPIView.as_view(), name='team-distribution-graph'),
    
    # Dashboard - Access controlled by permissions
    path('dashboard/quick-data/', DashboardQuickDataAPIView.as_view(), name='dashboard-quick-data'),
    path('dashboard/attrition-risk/', TeamAttritionRiskAPIView.as_view(), name='dashboard-attrition-risk'),
    path('dashboard/mental-health/', TeamMentalHealthAPIView.as_view(), name='dashboard-mental-health'),
    path('dashboard/utilization/', TeamUtilizationAPIView.as_view(), name='dashboard-utilization'),
    
    # Project Allocations - Access controlled by permissions
    path('allocations/', ProjectAllocationAPIView.as_view(), name='project-allocations'),
    path('allocations/<int:pk>/', ProjectAllocationAPIView.as_view(), name='project-allocation-detail'),
    path('project-team/<int:project_id>/', ProjectTeamAPIView.as_view(), name='project-team'),
    path('employee-allocation-summary/', EmployeeAllocationSummaryAPIView.as_view(), name='employee-allocation-summary'),
    
    # User Management
    path('users/search/', UserSearchAPIView.as_view(), name='user-search'),
    
    # Surveys - Role-based access controlled in views
    path('surveys/', SurveyListAPIView.as_view(), name='surveys'),
    path('surveys/<int:survey_id>/', SurveyDetailAPIView.as_view(), name='survey-detail'),
    path('surveys/<int:survey_id>/respond/', SurveyResponseAPIView.as_view(), name='survey-response'),
    path('my-survey-responses/', MySurveyResponsesAPIView.as_view(), name='my-survey-responses'),
    path('survey-management/', SurveyManagementAPIView.as_view(), name='survey-management'),
    path('surveys/manage/', SurveyManagementAPIView.as_view(), name='surveys-manage'),
    path('survey-management/<int:survey_id>/details/', SurveyDetailAPIView.as_view(), name='survey-details'),
    path('manager/publish-survey/', ManagerSurveyPublishAPIView.as_view(), name='manager-publish-survey'),
    
    # Conversations - Chat system
    # Conversation CRUD
    path('conversations/', ConversationListCreateView.as_view(), name='conversation-list-create'),
    path('conversations/<uuid:id>/', ConversationDetailView.as_view(), name='conversation-detail'),
    
    # Conversation messages
    path('conversations/<uuid:conversation_id>/messages/', ConversationMessageListView.as_view(), name='conversation-messages'),
    path('conversations/<uuid:conversation_id>/messages/add/', add_message_to_conversation, name='add-message'),
    
    # Conversation sharing
    path('conversations/<uuid:conversation_id>/shares/', ConversationShareListCreateView.as_view(), name='conversation-shares'),
    path('conversations/<uuid:conversation_id>/shares/<uuid:share_id>/', remove_conversation_share, name='remove-share'),
    path('shared-conversations/', get_shared_conversations, name='shared-conversations'),

    # Criticality
    path('criticality/vs-risk/', CriticalityVsRiskView.as_view(), name='criticality-vs-risk'),
    path('criticality/risk-distribution/', RiskDistributionView.as_view(), name='risk-distribution'),
    path('criticality/metrics/', CriticalityMetricsAPIView.as_view(), name='criticality-metrics'),
    path('criticality/trends/', CriticalityTrendsAPIView.as_view(), name='criticality-trends'),
]
