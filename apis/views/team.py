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
    
    def put(self, request):
        """Update employee profile data"""
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'error': 'user_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            profile = EmployeeProfile.objects.get(user_id=user_id)
        except EmployeeProfile.DoesNotExist:
            return Response({'error': 'Employee profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = EmployeeProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
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
