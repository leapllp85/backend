from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q, Prefetch, Case, When, IntegerField
from ..models import EmployeeProfile, ProjectAllocation, Project
from ..serializers import TeamMemberDetailSerializer, EmployeeProfileSerializer, ProjectAllocationSerializer
from ..permissions import IsManager, CanAccessTeamData
from collections import Counter


class TeamMemberPagination(PageNumberPagination):
    """Custom pagination for team members"""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class MyTeamAPIView(APIView):
    """API for My Team tabular data with all required columns - Manager only"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    pagination_class = TeamMemberPagination
    
    def get(self, request):
        """Get team members with all profile data - Manager only"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # If user is a manager, return team data; if associate, return own data
        if user_profile.is_manager:
            team_members = User.objects.filter(employee_profile__manager=user)
            context_message = f"Team data for manager: {user.get_full_name()}"
        else:
            # Associates can only see their own data
            team_members = User.objects.filter(id=user.id)
            context_message = f"Personal data for associate: {user.get_full_name()}"
        
        # Optimize query with better prefetching for faster aggregation
        team_members = team_members.select_related('employee_profile').prefetch_related(
            Prefetch('employee_allocations', 
                    queryset=ProjectAllocation.objects.select_related('project')),
            'employee_profile__manager'
        )
        
        # Add search functionality
        search_query = request.GET.get('search', '').strip()
        if search_query:
            team_members = team_members.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(username__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        
        # Apply pagination
        paginator = self.pagination_class()
        paginated_team_members = paginator.paginate_queryset(team_members, request)
        
        # Store total count before pagination for accurate team_size
        total_team_size = team_members.count()
        
        if paginated_team_members is not None:
            serializer = TeamMemberDetailSerializer(paginated_team_members, many=True)
            return paginator.get_paginated_response({
                'team_members': serializer.data,
                'manager_info': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'team_size': total_team_size
                },
                'search_query': search_query if search_query else None,
                'filtered_count': total_team_size
            })
        
        # Fallback for when pagination is not applied
        serializer = TeamMemberDetailSerializer(team_members, many=True)
        return Response({
            'team_members': serializer.data,
            'manager_info': {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'team_size': total_team_size
            },
            'search_query': search_query if search_query else None,
            'filtered_count': total_team_size
        })
    
    def put(self, request, employee_id=None):
        """Update employee profile data"""
        # Support both URL parameter and request body user_id for backward compatibility
        user_id = employee_id or request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if the requesting user is a manager and has permission to update this employee
        requesting_user = request.user
        try:
            requesting_profile = requesting_user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({'error': 'Employee profile not found for requesting user'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            target_profile = EmployeeProfile.objects.get(user_id=user_id)
        except EmployeeProfile.DoesNotExist:
            return Response({'error': 'Employee profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions: managers can update their team members, users can update themselves
        if requesting_profile.is_manager:
            # Manager can update team members
            if target_profile.manager != requesting_user:
                return Response({'error': 'Access denied. You can only update your team members.'}, status=status.HTTP_403_FORBIDDEN)
        else:
            # Non-managers can only update themselves
            if target_profile.user != requesting_user:
                return Response({'error': 'Access denied. You can only update your own profile.'}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = EmployeeProfileSerializer(target_profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            
            
            return Response({
                'message': 'Employee profile updated successfully',
                'data': serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AttritionGraphAPIView(APIView):
    """API for attrition graph based on Manager Assessment Risk - Manager only"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        """Get attrition data for bar graph - Manager only"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Optimized aggregation query with index hints
        risk_counts = EmployeeProfile.objects.filter(
            manager=user
        ).values('manager_assessment_risk').annotate(
            count=Count('id')
        ).order_by('manager_assessment_risk')
        
        # Format for bar graph
        graph_data = {
            'labels': [],
            'data': [],
            'backgroundColor': []
        }
        
        color_map = {
            'High': '#ff6b6b',
            'Medium': '#ffd93d', 
            'Low': '#6bcf7f'
        }
        
        for item in risk_counts:
            risk_level = item['manager_assessment_risk']
            count = item['count']
            
            graph_data['labels'].append(risk_level)
            graph_data['data'].append(count)
            graph_data['backgroundColor'].append(color_map.get(risk_level, '#gray'))
        
        return Response({
            'title': 'Team Attrition Risk Distribution',
            'type': 'bar',
            'data': graph_data
        })


class DistributionGraphAPIView(APIView):
    """API for distribution graph (donut chart) on triggers - Manager only"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        """Get trigger distribution for donut chart - Manager only"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get profiles for this manager's team only
        profiles = EmployeeProfile.objects.filter(manager=user)
        
        # Count all triggers (inner donut)
        all_triggers_count = Counter()
        primary_triggers_count = Counter()
        
        trigger_labels = {
            'MH': 'Mental Health',
            'MT': 'Motivation Factor', 
            'CO': 'Career Opportunities',
            'PR': 'Personal Reason'
        }
        
        for profile in profiles:
            # Count all triggers
            if profile.all_triggers:
                triggers = [t.strip() for t in profile.all_triggers.split(',') if t.strip()]
                for trigger in triggers:
                    if trigger in trigger_labels:
                        all_triggers_count[trigger] += 1
            
            # Count primary triggers
            if profile.primary_trigger:
                primary_triggers_count[profile.primary_trigger] += 1
        
        # Format for donut chart
        inner_data = {
            'labels': [trigger_labels[k] for k in all_triggers_count.keys()],
            'data': list(all_triggers_count.values()),
            'backgroundColor': ['#ff6b6b', '#4ecdc4', '#45b7d1', '#f9ca24']
        }
        
        outer_data = {
            'labels': [trigger_labels[k] for k in primary_triggers_count.keys()],
            'data': list(primary_triggers_count.values()),
            'backgroundColor': ['#ff9ff3', '#54a0ff', '#5f27cd', '#00d2d3']
        }
        
        return Response({
            'title': 'Trigger Distribution Analysis',
            'type': 'doughnut',
            'inner': {
                'title': 'All Issues',
                'data': inner_data
            },
            'outer': {
                'title': 'Primary Issues',
                'data': outer_data
            }
        })


class TeamAnalyticsAPIView(APIView):
    """Combined analytics endpoint for team insights - Manager only"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        """Get comprehensive team analytics - Manager only"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Optimized single query for team analytics
        from ..utils.db_optimization import get_team_analytics_optimized
        return Response(get_team_analytics_optimized(user))


class TeamStatsAPIView(APIView):
    """API for team statistics used in Profile component"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get team stats including member count and utilization"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get team members based on user role and calculate stats in single query
        if user_profile.is_manager:
            # Only count users who have employee profiles and report to this manager
            team_filter = Q(employee_profile__manager=user, employee_profile__isnull=False)
        else:
            # Associates can only see their own data
            team_filter = Q(id=user.id)
        
        # Single aggregation query for all stats with proper filtering
        from ..models import ProjectAllocation
        stats = User.objects.filter(team_filter).aggregate(
            team_count=Count('id'),
            avg_utilization=Avg(
                'employee_allocations__allocation_percentage',
                filter=Q(employee_allocations__project__status='Active', employee_allocations__is_active=True)
            )
        )
        
        avg_utilization = stats['avg_utilization'] or 0
        
        return Response({
            'team_members_count': stats['team_count'],
            'average_utilization': round(avg_utilization, 1),
            'utilization_percentage': f"{round(avg_utilization)}%"
        })


class ProjectStatsAPIView(APIView):
    """API for project statistics used in Profile component"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get essential project stats without detailed project data"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        from ..models import Project
        
        # Get project filter based on user role
        if user_profile.is_manager:
            project_filter = Q(project_allocations__employee__employee_profile__manager=user)
        else:
            project_filter = Q(project_allocations__employee=user)
        
        # Single aggregation query for all project statistics
        stats = Project.objects.filter(project_filter).distinct().aggregate(
            total_projects=Count('id'),
            high_risk_projects=Count('id', filter=Q(criticality='High')),
            active_projects=Count('id', filter=Q(status='Active')),
            completed_projects=Count('id', filter=Q(status='Completed'))
        )
        
        total_projects = stats['total_projects']
        completion_rate = round((stats['completed_projects'] / total_projects * 100), 1) if total_projects > 0 else 0
        
        return Response({
            'total_projects': total_projects,
            'high_risk_projects': stats['high_risk_projects'],
            'active_projects': stats['active_projects'],
            'completed_projects': stats['completed_projects'],
            'completion_rate': completion_rate
        })


class MetricsAPIView(APIView):
    """API for dashboard metrics used in Profile component"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get essential metrics without detailed project information"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get team filter based on user role
        if user_profile.is_manager:
            team_filter = Q(manager=user)
        else:
            team_filter = Q(user=user)
        
        # Single aggregation query to calculate all metrics
        from django.db.models import Case, When, IntegerField, FloatField
        
        metrics = EmployeeProfile.objects.filter(team_filter).aggregate(
            total_count=Count('id'),
            mental_health_avg=Avg(
                Case(
                    When(mental_health='High', then=80),
                    When(mental_health='Medium', then=60),
                    When(mental_health='Low', then=40),
                    default=50,
                    output_field=IntegerField()
                )
            ),
            attrition_risk_avg=Avg(
                Case(
                    When(manager_assessment_risk='Low', then=85),
                    When(manager_assessment_risk='Medium', then=60),
                    When(manager_assessment_risk='High', then=30),
                    default=50,
                    output_field=IntegerField()
                )
            ),
            motivation_avg=Avg(
                Case(
                    When(motivation_factor='High', then=80),
                    When(motivation_factor='Medium', then=60),
                    When(motivation_factor='Low', then=40),
                    default=50,
                    output_field=IntegerField()
                )
            )
        )
        
        if metrics['total_count'] == 0:
            return Response({
                'mental_health': 0,
                'attrition_risk': 0,
                'team_wellness': 0
            })
        
        mental_health_avg = metrics['mental_health_avg'] or 50
        attrition_risk_avg = metrics['attrition_risk_avg'] or 50
        motivation_avg = metrics['motivation_avg'] or 50
        team_wellness = (mental_health_avg + motivation_avg) / 2
        
        return Response({
            'mental_health': round(mental_health_avg),
            'attrition_risk': round(attrition_risk_avg),
            'team_wellness': round(team_wellness)
        })


class NotificationsAPIView(APIView):
    """API for notifications used in Profile component"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get recent notifications for the user"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        notifications = []
        
        # Generate notifications based on team data for managers
        if user_profile.is_manager:
            team_members = User.objects.filter(employee_profile__manager=user)
            profiles = EmployeeProfile.objects.filter(user__in=team_members)
            
            # High attrition risk notification
            high_risk_count = profiles.filter(manager_assessment_risk='High').count()
            if high_risk_count > 0:
                notifications.append({
                    'id': 'attrition_risk',
                    'title': 'High Attrition Risk',
                    'description': f'{high_risk_count} team members show high risk of attrition',
                    'timestamp': '10 min ago',
                    'type': 'error'
                })
            
            # Mental health concerns
            mh_concerns = profiles.filter(mental_health='Low').count()
            if mh_concerns > 0:
                notifications.append({
                    'id': 'mental_health',
                    'title': 'Mental Health Alert',
                    'description': f'{mh_concerns} team members need mental health support',
                    'timestamp': '25 min ago',
                    'type': 'warning'
                })
            
            # Project deadlines
            from ..models import Project
            from django.utils import timezone
            from datetime import timedelta
            
            upcoming_deadlines = Project.objects.filter(
                project_allocations__employee__in=team_members,
                go_live_date__lte=timezone.now() + timedelta(days=7),
                status='Active'
            ).distinct().count()
            
            if upcoming_deadlines > 0:
                notifications.append({
                    'id': 'project_deadlines',
                    'title': 'Upcoming Deadlines',
                    'description': f'{upcoming_deadlines} projects have deadlines this week',
                    'timestamp': '1 hour ago',
                    'type': 'info'
                })
        
        # Add some general notifications if list is empty
        if not notifications:
            notifications = [
                {
                    'id': 'welcome',
                    'title': 'Welcome to Dashboard',
                    'description': 'Your team data is up to date',
                    'timestamp': '2 hours ago',
                    'type': 'info'
                }
            ]
        
        return Response({
            'notifications': notifications,
            'unread_count': len([n for n in notifications if n['type'] in ['error', 'warning']])
        })


class ProjectRisksAPIView(APIView):
    """API for project risks - returns top 5 high-risk projects"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get top 5 high-risk projects with summary statistics"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        from ..models import Project
        
        # Get project filter based on user role
        if user_profile.is_manager:
            project_filter = Q(project_allocations__employee__employee_profile__manager=user)
        else:
            project_filter = Q(project_allocations__employee=user)
        
        # Get all projects for statistics
        projects_queryset = Project.objects.filter(project_filter).distinct()
        
        # Single aggregation query for summary statistics
        risk_stats = projects_queryset.aggregate(
            total_projects=Count('id'),
            high_risk_count=Count('id', filter=Q(criticality='High')),
            medium_risk_count=Count('id', filter=Q(criticality='Medium')),
            low_risk_count=Count('id', filter=Q(criticality='Low'))
        )
        
        # Get top 5 projects prioritizing high-risk first, then medium-risk
        # Use database ordering to prioritize by criticality, then by creation date
        top_risk_projects = projects_queryset.filter(
            criticality__in=['High', 'Medium']
        ).select_related().annotate(
            criticality_priority=Case(
                When(criticality='High', then=1),
                When(criticality='Medium', then=2),
                default=3,
                output_field=IntegerField()
            )
        ).order_by('criticality_priority', '-created_at')[:5]
        
        # Format projects data
        projects_data = []
        for project in top_risk_projects:
            # Get team member count for this project
            team_count = project.project_allocations.filter(is_active=True).count()
            
            projects_data.append({
                'id': project.id,
                'title': project.title,
                'description': project.description[:100] + '...' if len(project.description) > 100 else project.description,
                'criticality': project.criticality,
                'status': project.status,
                'go_live_date': project.go_live_date,
                'team_members_count': team_count,
                'created_at': project.created_at
            })
        
        total_projects = risk_stats['total_projects']
        risk_percentage = round((risk_stats['high_risk_count'] / total_projects * 100), 1) if total_projects > 0 else 0
        
        return Response({
            'summary': {
                'total_projects': total_projects,
                'high_risk_count': risk_stats['high_risk_count'],
                'medium_risk_count': risk_stats['medium_risk_count'],
                'low_risk_count': risk_stats['low_risk_count'],
                'risk_percentage': risk_percentage
            },
            'projects': projects_data
        })
