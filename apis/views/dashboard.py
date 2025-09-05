from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Q, F, Sum
from ..models import EmployeeProfile, ProjectAllocation, Project
from ..permissions import CanAccessTeamData
from collections import Counter
from datetime import datetime, timedelta

class DashboardQuickDataAPIView(APIView):
    """API for dashboard quick data widgets"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get all dashboard metrics in one call"""
        
        # Get all employee profiles
        profiles = EmployeeProfile.objects.select_related('user').all()
        total_members = profiles.count()
        
        if total_members == 0:
            return Response({
                'team_attrition_risk': 0,
                'team_mental_health': 0,
                'avg_utilization': 0,
                'top_talent': [],
                'average_age': 0,
                'total_team_members': 0
            })
        
        # 1. Team Attrition Risk (percentage of high-risk employees)
        high_risk_count = profiles.filter(manager_assessment_risk='High').count()
        team_attrition_risk = round((high_risk_count / total_members) * 100, 1)
        
        # 2. Team Mental Health (average mental health score)
        risk_scores = {'High': 3, 'Medium': 2, 'Low': 1}
        mh_scores = [risk_scores.get(p.mental_health, 2) for p in profiles]
        avg_mh_score = round(sum(mh_scores) / len(mh_scores), 2)
        
        # Convert back to percentage (3=100%, 2=66%, 1=33%)
        team_mental_health = round((avg_mh_score / 3) * 100, 1)
        
        # 3. Average Utilization of Team Members
        active_allocations = ProjectAllocation.objects.filter(is_active=True)
        if active_allocations.exists():
            total_allocation = active_allocations.aggregate(
                total=Sum('allocation_percentage')
            )['total'] or 0
            active_employees = active_allocations.values('employee').distinct().count()
            avg_utilization = round(total_allocation / active_employees if active_employees > 0 else 0, 1)
        else:
            avg_utilization = 0
        
        # 4. Top Talent (Top 3 employees from project criticality)
        top_talent = self.get_top_talent()
        
        # 5. Average Age of Team
        ages = [p.age for p in profiles if p.age]
        average_age = round(sum(ages) / len(ages) if ages else 0, 1)
        
        return Response({
            'team_attrition_risk': team_attrition_risk,
            'team_mental_health': team_mental_health,
            'avg_utilization': avg_utilization,
            'top_talent': top_talent,
            'average_age': average_age,
            'total_team_members': total_members
        })
    
    def get_top_talent(self):
        """Get top 3 employees based on project criticality"""
        # Get employees with their highest project criticality
        employees_with_criticality = []
        
        user = self.request.user
        user_profile = user.employee_profile
        
        # Get relevant users based on role
        if user_profile.is_manager:
            team_members = User.objects.filter(employee_profile__manager=user)
            scope = 'team'
        else:
            team_members = User.objects.filter(id=user.id)
            scope = 'personal'
        
        users = team_members.prefetch_related('employee_allocations__project')
        
        criticality_scores = {'High': 3, 'Medium': 2, 'Low': 1}
        
        for user in users:
            active_allocations = user.employee_allocations.filter(is_active=True)
            if active_allocations.exists():
                # Get highest criticality from active projects
                max_criticality = max(
                    criticality_scores.get(alloc.project.criticality, 1) 
                    for alloc in active_allocations
                )
                criticality_label = next(
                    label for label, score in criticality_scores.items() 
                    if score == max_criticality
                )
            else:
                max_criticality = 1
                criticality_label = 'Low'
            
            employees_with_criticality.append({
                'user_info': {
                    'name': f"{user.first_name} {user.last_name}",
                    'role': user_profile.role,
                    'is_manager': user_profile.is_manager,
                    'scope': scope,
                    'data_size': team_members.count()
                },
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'age': user.employee_profile.age,
                'mental_health': user.employee_profile.mental_health,
                'criticality_score': max_criticality,
                'criticality_label': criticality_label,
                'profile_pic': getattr(user.employee_profile, 'profile_pic', None)
            })
        
        # Sort by criticality score and return top 3
        top_employees = sorted(
            employees_with_criticality, 
            key=lambda x: x['criticality_score'], 
            reverse=True
        )[:3]
        
        return top_employees


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
