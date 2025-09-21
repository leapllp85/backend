from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q
from ..models import EmployeeProfile, ProjectAllocation, Project
from ..serializers import TeamMemberDetailSerializer, EmployeeProfileSerializer, ProjectAllocationSerializer
from ..permissions import IsManager, CanAccessTeamData
from collections import Counter


class MyTeamAPIView(APIView):
    """API for My Team tabular data with all required columns - Manager only"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
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
        
        # Get team members reporting to this manager
        team_members = team_members.select_related('employee_profile').prefetch_related('employee_allocations__project')
        
        serializer = TeamMemberDetailSerializer(team_members, many=True)
        return Response({
            'team_members': serializer.data,
            'manager_info': {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'team_size': team_members.count()
            }
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
    permission_classes = [IsAuthenticated]
    
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
        
        # Count employees by manager assessment risk for this manager's team
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
    permission_classes = [IsAuthenticated]
    
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
    permission_classes = [IsAuthenticated]
    
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
        
        # Get profiles for this manager's team only
        profiles = EmployeeProfile.objects.filter(manager=user).select_related('user')
        
        # Calculate various metrics
        total_members = profiles.count()
        
        if total_members == 0:
            return Response({
                'total_members': 0,
                'avg_mental_health_score': 0,
                'high_risk_count': 0,
                'avg_age': 0,
                'risk_distribution': {}
            })
        
        # Risk score mapping
        risk_scores = {'High': 3, 'Medium': 2, 'Low': 1}
        
        # Mental health average
        mh_scores = [risk_scores.get(p.mental_health, 2) for p in profiles]
        avg_mh_score = sum(mh_scores) / len(mh_scores)
        
        # High risk count (manager assessment)
        high_risk_count = profiles.filter(manager_assessment_risk='High').count()
        
        # Average age
        ages = [p.age for p in profiles if p.age]
        avg_age = sum(ages) / len(ages) if ages else 0
        
        # Risk distribution
        risk_dist = profiles.values('manager_assessment_risk').annotate(
            count=Count('id')
        )
        
        return Response({
            'total_members': total_members,
            'avg_mental_health_score': round(avg_mh_score, 2),
            'high_risk_count': high_risk_count,
            'avg_age': round(avg_age, 1),
            'risk_distribution': {item['manager_assessment_risk']: item['count'] for item in risk_dist}
        })


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
        
        # Get team members based on user role
        if user_profile.is_manager:
            team_members = User.objects.filter(employee_profile__manager=user)
        else:
            team_members = User.objects.filter(id=user.id)
        
        team_count = team_members.count()
        
        # Calculate average utilization from project allocations
        from ..models import ProjectAllocation
        allocations = ProjectAllocation.objects.filter(
            employee__in=team_members,
            project__status='Active'
        )
        
        if allocations.exists():
            avg_utilization = allocations.aggregate(
                avg_util=Avg('allocation_percentage')
            )['avg_util'] or 0
        else:
            avg_utilization = 0
        
        return Response({
            'team_members_count': team_count,
            'average_utilization': round(avg_utilization, 1),
            'utilization_percentage': f"{round(avg_utilization)}%"
        })


class ProjectStatsAPIView(APIView):
    """API for project statistics used in Profile component"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get project stats including high-risk project count"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        from ..models import Project
        
        # Get projects based on user role
        if user_profile.is_manager:
            # Manager sees projects where they have team members allocated
            team_members = User.objects.filter(employee_profile__manager=user)
            projects = Project.objects.filter(
                project_allocations__employee__in=team_members
            ).distinct()
        else:
            # Associates see their own projects
            projects = Project.objects.filter(project_allocations__employee=user)
        
        total_projects = projects.count()
        high_risk_projects = projects.filter(criticality='High').count()
        active_projects = projects.filter(status='Active').count()
        
        return Response({
            'total_projects': total_projects,
            'high_risk_projects': high_risk_projects,
            'active_projects': active_projects
        })


class MetricsAPIView(APIView):
    """API for dashboard metrics used in Profile component"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get project metrics including mental health, attrition risk, and project health"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get team members based on user role
        if user_profile.is_manager:
            team_members = User.objects.filter(employee_profile__manager=user)
        else:
            team_members = User.objects.filter(id=user.id)
        
        profiles = EmployeeProfile.objects.filter(user__in=team_members)
        
        if not profiles.exists():
            return Response({
                'mental_health': 0,
                'attrition_risk': 0,
                'project_health': 0
            })
        
        # Calculate mental health score (1-5 scale converted to percentage)
        mh_mapping = {'High': 80, 'Medium': 60, 'Low': 40}
        mh_scores = [mh_mapping.get(p.mental_health, 50) for p in profiles]
        mental_health_avg = sum(mh_scores) / len(mh_scores)
        
        # Calculate attrition risk (inverse of risk - lower risk = higher score)
        risk_mapping = {'Low': 85, 'Medium': 60, 'High': 30}
        risk_scores = [risk_mapping.get(p.manager_assessment_risk, 50) for p in profiles]
        attrition_risk_avg = sum(risk_scores) / len(risk_scores)
        
        # Calculate project health based on project criticality
        from ..models import Project
        if user_profile.is_manager:
            projects = Project.objects.filter(
                project_allocations__employee__in=team_members
            ).distinct()
        else:
            projects = Project.objects.filter(project_allocations__employee=user)
        
        if projects.exists():
            # Project health based on criticality distribution
            total_projects = projects.count()
            high_crit = projects.filter(criticality='High').count()
            medium_crit = projects.filter(criticality='Medium').count()
            low_crit = projects.filter(criticality='Low').count()
            
            # Calculate weighted score (Low=100, Medium=70, High=40)
            project_health = ((low_crit * 100) + (medium_crit * 70) + (high_crit * 40)) / total_projects
        else:
            project_health = 75  # Default when no projects
        
        return Response({
            'mental_health': round(mental_health_avg),
            'attrition_risk': round(attrition_risk_avg), 
            'project_health': round(project_health)
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
    """API for project risks used in Profile component"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get project risks with detailed information"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        from ..models import Project, ProjectAllocation
        from django.db.models import Count
        
        # Get projects based on user role
        if user_profile.is_manager:
            team_members = User.objects.filter(employee_profile__manager=user)
            projects = Project.objects.filter(
                project_allocations__employee__in=team_members
            ).distinct()
        else:
            projects = Project.objects.filter(project_allocations__employee=user)
        
        project_risks = []
        
        for project in projects:
            # Count team members on this project
            member_count = ProjectAllocation.objects.filter(project=project).count()
            
            # Calculate progress (mock calculation based on project dates)
            from django.utils import timezone
            if project.go_live_date and project.start_date:
                total_days = (project.go_live_date - project.start_date).days
                elapsed_days = (timezone.now().date() - project.start_date).days
                progress = max(0, min(100, (elapsed_days / total_days) * 100)) if total_days > 0 else 0
            else:
                progress = 50  # Default progress
            
            # Map criticality to risk level
            risk_level_map = {
                'High': 'High Risk',
                'Medium': 'Medium Risk', 
                'Low': 'Low Risk'
            }
            
            project_risks.append({
                'id': str(project.id),
                'name': project.title,
                'progress': round(progress),
                'riskLevel': risk_level_map.get(project.criticality, 'Medium Risk'),
                'tasks': project.id * 1000 + 234,  # Mock task count
                'members': member_count,
                'dueDate': project.go_live_date.strftime('%d %b %Y') if project.go_live_date else 'No deadline'
            })
        
        # Sort by risk level (High first)
        risk_priority = {'High Risk': 0, 'Medium Risk': 1, 'Low Risk': 2}
        project_risks.sort(key=lambda x: risk_priority.get(x['riskLevel'], 1))
        
        return Response({
            'projects': project_risks,
            'total_projects': len(project_risks),
            'high_risk_count': len([p for p in project_risks if p['riskLevel'] == 'High Risk'])
        })
