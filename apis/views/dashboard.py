from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q, F, Sum, Case, When, FloatField
from ..models import EmployeeProfile, ProjectAllocation, Project
from ..permissions import CanAccessTeamData
from collections import Counter
from datetime import datetime, timedelta

class DashboardQuickDataAPIView(APIView):
    """API for dashboard quick data widgets"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get quick dashboard data using database aggregations"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({'error': 'Employee profile not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get team filter based on role
        if user_profile.is_manager:
            team_filter = Q(employee_profile__manager=user)
            profile_filter = Q(manager=user)
        else:
            team_filter = Q(id=user.id)
            profile_filter = Q(user=user)
        
        # Single aggregation query for team stats
        from ..models import ProjectAllocation
        
        team_stats = User.objects.filter(team_filter).aggregate(
            total_members=Count('id'),
            avg_utilization=Avg(
                'employee_allocations__allocation_percentage',
                filter=Q(employee_allocations__is_active=True)
            )
        )
        
        # Single aggregation query for profile-based metrics
        profile_stats = EmployeeProfile.objects.filter(profile_filter).aggregate(
            total_profiles=Count('id'),
            high_risk_count=Count('id', filter=Q(manager_assessment_risk='High')),
            mental_health_avg=Avg(
                Case(
                    When(mental_health='High', then=3),
                    When(mental_health='Medium', then=2),
                    When(mental_health='Low', then=1),
                    default=2,
                    output_field=FloatField()
                )
            ),
            average_age=Avg('age')
        )
        
        # Calculate derived metrics
        total_profiles = profile_stats['total_profiles'] or 1
        team_attrition_risk = round((profile_stats['high_risk_count'] / total_profiles) * 100, 1)
        team_mental_health = round((profile_stats['mental_health_avg'] or 2) * 33.33, 1)
        avg_utilization = team_stats['avg_utilization'] or 0
        
        # Get top talent using optimized method
        top_talent = self.get_top_talent()
        
        return Response({
            'team_attrition_risk': team_attrition_risk,
            'team_mental_health': team_mental_health,
            'avg_utilization': round(avg_utilization, 1),
            'top_talent': top_talent,
            'average_age': round(profile_stats['average_age'] or 0, 1),
            'total_team_members': team_stats['total_members']
        })
    
    def get_top_talent(self):
        """Get top 3 employees based on performance metrics using database aggregation"""
        user = self.request.user
        user_profile = user.employee_profile
        
        # Get team filter based on role
        if user_profile.is_manager:
            team_filter = Q(employee_profile__manager=user)
        else:
            team_filter = Q(id=user.id)
        
        # Use database aggregation to calculate performance scores
        from django.db.models import Case, When, FloatField, F
        
        top_employees = User.objects.filter(team_filter).select_related('employee_profile').annotate(
            mental_health_score=Case(
                When(employee_profile__mental_health='High', then=3),
                When(employee_profile__mental_health='Medium', then=2),
                When(employee_profile__mental_health='Low', then=1),
                default=2,
                output_field=FloatField()
            ),
            motivation_score=Case(
                When(employee_profile__motivation_factor='High', then=3),
                When(employee_profile__motivation_factor='Medium', then=2),
                When(employee_profile__motivation_factor='Low', then=1),
                default=2,
                output_field=FloatField()
            ),
            career_score=Case(
                When(employee_profile__career_opportunities='High', then=3),
                When(employee_profile__career_opportunities='Medium', then=2),
                When(employee_profile__career_opportunities='Low', then=1),
                default=2,
                output_field=FloatField()
            ),
            performance_score=(F('mental_health_score') + F('motivation_score') + F('career_score')) / 3
        ).order_by('-performance_score')[:3]
        
        # Convert to list with required fields
        return [{
            'id': emp.id,
            'username': emp.username,
            'first_name': emp.first_name,
            'last_name': emp.last_name,
            'age': emp.employee_profile.age,
            'mental_health': emp.employee_profile.mental_health,
            'performance_score': round(float(emp.performance_score), 2),
            'profile_pic': getattr(emp.employee_profile, 'profile_pic', None)
        } for emp in top_employees]


class TeamAttritionRiskAPIView(APIView):
    """Specific API for team attrition risk analysis"""
    
    def get(self, request):
        """Get detailed attrition risk breakdown"""
        profiles = EmployeeProfile.objects.all()
        total = profiles.count()
        
        if total == 0:
            return Response({
                'total_employees': 0,
                'risk_breakdown': {},
                'percentage_breakdown': {}
            })
        
        # Count by manager assessment risk
        risk_counts = profiles.values('manager_assessment_risk').annotate(
            count=Count('id')
        )
        
        risk_breakdown = {item['manager_assessment_risk']: item['count'] for item in risk_counts}
        percentage_breakdown = {
            risk: round((count / total) * 100, 1) 
            for risk, count in risk_breakdown.items()
        }
        
        return Response({
            'total_employees': total,
            'risk_breakdown': risk_breakdown,
            'percentage_breakdown': percentage_breakdown,
            'high_risk_percentage': percentage_breakdown.get('High', 0)
        })


class TeamMentalHealthAPIView(APIView):
    """Specific API for team mental health analysis"""
    
    def get(self, request):
        """Get detailed mental health breakdown"""
        profiles = EmployeeProfile.objects.all()
        total = profiles.count()
        
        if total == 0:
            return Response({
                'total_employees': 0,
                'mental_health_breakdown': {},
                'average_score': 0
            })
        
        # Count by mental health levels
        mh_counts = profiles.values('mental_health').annotate(
            count=Count('id')
        )
        
        mh_breakdown = {item['mental_health']: item['count'] for item in mh_counts}
        
        # Calculate average score
        risk_scores = {'High': 3, 'Medium': 2, 'Low': 1}
        scores = [risk_scores.get(p.mental_health, 2) for p in profiles]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return Response({
            'total_employees': total,
            'mental_health_breakdown': mh_breakdown,
            'average_score': round(avg_score, 2),
            'percentage_score': round((avg_score / 3) * 100, 1)
        })


class TeamUtilizationAPIView(APIView):
    """Specific API for team utilization analysis"""
    
    def get(self, request):
        """Get detailed utilization breakdown"""
        active_allocations = ProjectAllocation.objects.filter(is_active=True).select_related('employee', 'project')
        
        if not active_allocations.exists():
            return Response({
                'total_allocated_employees': 0,
                'average_utilization': 0,
                'utilization_breakdown': []
            })
        
        # Group by employee
        employee_utilization = {}
        for allocation in active_allocations:
            employee_id = allocation.employee.id
            if employee_id not in employee_utilization:
                employee_utilization[employee_id] = {
                    'employee_name': allocation.employee.username,
                    'total_allocation': 0,
                    'projects': []
                }
            
            employee_utilization[employee_id]['total_allocation'] += allocation.allocation_percentage
            employee_utilization[employee_id]['projects'].append({
                'project_name': allocation.project.title,
                'allocation_percentage': allocation.allocation_percentage
            })
        
        # Calculate average
        total_allocation = sum(emp['total_allocation'] for emp in employee_utilization.values())
        avg_utilization = total_allocation / len(employee_utilization) if employee_utilization else 0
        
        return Response({
            'total_allocated_employees': len(employee_utilization),
            'average_utilization': round(avg_utilization, 1),
            'utilization_breakdown': list(employee_utilization.values())
        })
