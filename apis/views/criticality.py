from apis.models.employees import CRITICALITY_SCORE_MAP
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apis.permissions import IsManager
from apis.serializers import CriticalityVsRiskSerializer, RiskDistributionSerializer
from apis.models import EmployeeProfile
from rest_framework import status
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone
from datetime import datetime, timedelta
import hashlib
from ..models import EmployeeProfile, ProjectAllocation
from ..serializers import (
    CriticalityMetricsSerializer,
    CriticalityTrendSerializer,
    CriticalityTrendsInputSerializer,
    EmployeeProfileSerializer,
    ProjectAllocationSerializer
)



class CriticalityVsRiskView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        user_id = request.user.id
        employee_profile = EmployeeProfile.objects.filter(manager=user_id)
        # Scatter Graph Data with Mental Health and Career Growth score against each employee
        scatter_data = []
        mental_health_scores = []
        career_growth_scores = []
        for profile in employee_profile:
            scatter_data.append({
                "criticality": profile.employee_project_criticality,
                "risk": profile.suggested_risk,
                "employee_name": profile.user.get_full_name()
            })
            mental_health_scores.append(profile.mental_health_score())
            career_growth_scores.append(profile.career_opportunities_score())
        data = {
            "work_wellness": CRITICALITY_SCORE_MAP[sum(mental_health_scores) // len(mental_health_scores)],
            "career_growth": CRITICALITY_SCORE_MAP[sum(career_growth_scores) // len(career_growth_scores)],
            "scatter_data": scatter_data,
        }
        serializer = CriticalityVsRiskSerializer(data)
        return Response({"success": True, "data": serializer.data, "message": "Risk analysis retrieved successfully"})


class RiskDistributionView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        user_id = request.user.id
        employee_profile = EmployeeProfile.objects.filter(manager=user_id)
        data = {
            "mental_health": {
                "high": employee_profile.filter(mental_health='High').count(), 
                "medium": employee_profile.filter(mental_health='Medium').count(), 
                "low": employee_profile.filter(mental_health='Low').count()
            },
            "motivation": {
                "high": employee_profile.filter(motivation_factor='High').count(), 
                "medium": employee_profile.filter(motivation_factor='Medium').count(), 
                "low": employee_profile.filter(motivation_factor='Low').count()
            },
            "career_opportunities": {
                "high": employee_profile.filter(career_opportunities='High').count(), 
                "medium": employee_profile.filter(career_opportunities='Medium').count(), 
                "low": employee_profile.filter(career_opportunities='Low').count()
            },
            "personal_factors": {
                "high": employee_profile.filter(personal_reason='High').count(), 
                "medium": employee_profile.filter(personal_reason='Medium').count(), 
                "low": employee_profile.filter(personal_reason='Low').count()
            },
        }
        serializer = RiskDistributionSerializer(data)
        return Response({"success": True, "data": serializer.data, "message": "Risk distribution retrieved successfully"})

class CriticalityMetricsAPIView(APIView):
    """
    Get criticality metrics for the authenticated user
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get current criticality metrics for the authenticated user"""
        try:
            user = request.user
            
            # Get or create employee profile
            employee_profile, created = EmployeeProfile.objects.get_or_create(
                user=user,
                defaults={
                    'age': 25,
                    'mental_health': 'Medium',
                    'motivation_factor': 'Medium',
                    'career_opportunities': 'Medium',
                    'personal_reason': 'Medium',
                    'manager_assessment_risk': 'Medium'
                }
            )
            
            # Calculate metrics based on user's data
            mental_health_risk = employee_profile.mental_health
            attrition_risk = employee_profile.suggested_risk
            
            # Get projects at risk (high criticality projects)
            projects_at_risk = ProjectAllocation.objects.filter(
                employee=user,
                is_active=True,
                criticality='High'
            ).count()
            
            # Calculate average utilization using existing relationship
            active_allocations = user.employee_allocations.filter(is_active=True)
            avg_utilization = active_allocations.aggregate(
                avg=Avg('allocation_percentage')
            )['avg'] or 0
            
            # Calculate overall score based on risk factors
            overall_score = self._calculate_overall_score(employee_profile, avg_utilization)
            
            # Prepare data for serialization
            metrics_data = {
                'mental_health_risk': mental_health_risk,
                'attrition_risk': attrition_risk,
                'projects_at_risk': projects_at_risk,
                'avg_utilization': round(avg_utilization, 1),
                'overall_score': overall_score,
                'last_updated': employee_profile.updated_at
            }
            
            # Serialize the data
            serializer = CriticalityMetricsSerializer(data=metrics_data)
            if serializer.is_valid():
                return Response({
                    'success': True,
                    'data': serializer.validated_data
                }, status=status.HTTP_200_OK)
            else:
                return Response({
                    'success': False,
                    'message': 'Invalid data format',
                    'errors': serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _calculate_overall_score(self, profile, utilization):
        """
        Calculate overall score based on various risk factors
        Higher score means better (lower risk)
        """
        # Risk factors (inverted for scoring - lower risk = higher score)
        risk_scores = {
            'High': 25,
            'Medium': 50,
            'Low': 75
        }
        
        mental_health_score = risk_scores.get(profile.mental_health, 50)
        motivation_score = risk_scores.get(profile.motivation_factor, 50)
        career_score = risk_scores.get(profile.career_opportunities, 50)
        personal_score = risk_scores.get(profile.personal_reason, 50)
        
        # Utilization score (optimal around 70-80%)
        if 70 <= utilization <= 80:
            utilization_score = 75
        elif 60 <= utilization < 70 or 80 < utilization <= 90:
            utilization_score = 60
        elif utilization < 60:
            utilization_score = 40
        else:  # > 90%
            utilization_score = 25
            
        # Weighted average
        total_score = (
            mental_health_score * 0.3 +
            motivation_score * 0.2 +
            career_score * 0.2 +
            personal_score * 0.15 +
            utilization_score * 0.15
        )
        
        return round(total_score, 1)


class CriticalityTrendsAPIView(APIView):
    """
    Get criticality trends for the specified number of days
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get criticality trends for the specified number of days"""
        try:
            # Validate input parameters
            input_serializer = CriticalityTrendsInputSerializer(data=request.GET)
            if not input_serializer.is_valid():
                return Response({
                    'success': False,
                    'message': 'Invalid parameters',
                    'errors': input_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            user = request.user
            days = input_serializer.validated_data['days']
            
            # Get employee profile using existing serializer pattern
            try:
                employee_profile = EmployeeProfile.objects.get(user=user)
            except EmployeeProfile.DoesNotExist:
                # Create default profile if doesn't exist
                employee_profile = EmployeeProfile.objects.create(
                    user=user,
                    age=25,
                    mental_health='Medium',
                    motivation_factor='Medium',
                    career_opportunities='Medium',
                    personal_reason='Medium',
                    manager_assessment_risk='Medium'
                )
            
            # Generate trend data for the requested period
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=days-1)  # Include today
            
            trends_data = []
            current_date = start_date
            
            while current_date <= end_date:
                # Get utilization for this date using existing relationship
                utilization = self._get_utilization_for_date(user, current_date)
                
                # Calculate scores
                mental_health_score = self._risk_to_score(employee_profile.mental_health)
                attrition_score = self._risk_to_score(employee_profile.suggested_risk)
                overall_score = self._calculate_daily_overall_score(
                    employee_profile, utilization, current_date
                )
                
                trend_item = {
                    'date': current_date,
                    'overall_score': overall_score,
                    'mental_health': mental_health_score,
                    'attrition_risk': attrition_score,
                    'utilization': utilization
                }
                
                trends_data.append(trend_item)
                current_date += timedelta(days=1)
            
            # Serialize the trends data
            serializer = CriticalityTrendSerializer(trends_data, many=True)
            
            return Response({
                'success': True,
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_utilization_for_date(self, user, date):
        """Get utilization for a specific date using existing relationships"""
        # Get active allocations for the date using the correct relationship
        allocations = user.employee_allocations.filter(
            start_date__lte=date,
            is_active=True
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=date)
        )
        
        total_allocation = sum(allocation.allocation_percentage for allocation in allocations)
        return min(round(total_allocation, 1), 100.0)  # Cap at 100%
    
    def _risk_to_score(self, risk_level):
        """Convert risk level to score (0-100)"""
        risk_scores = {
            'High': 25,
            'Medium': 50,
            'Low': 75
        }
        return risk_scores.get(risk_level, 50)
    
    def _calculate_daily_overall_score(self, profile, utilization, date):
        """Calculate overall score for a specific day"""
        mental_health_score = self._risk_to_score(profile.mental_health)
        motivation_score = self._risk_to_score(profile.motivation_factor)
        career_score = self._risk_to_score(profile.career_opportunities)
        personal_score = self._risk_to_score(profile.personal_reason)
        
        # Utilization score
        if 70 <= utilization <= 80:
            utilization_score = 75
        elif 60 <= utilization < 70 or 80 < utilization <= 90:
            utilization_score = 60
        elif utilization < 60:
            utilization_score = 40
        else:
            utilization_score = 25
        
        # Add some variation based on date for demo purposes
        # In production, you might want to use actual historical data
        date_hash = int(hashlib.md5(date.isoformat().encode()).hexdigest(), 16)
        variation = (date_hash % 21) - 10  # -10 to +10 variation
        
        total_score = (
            mental_health_score * 0.3 +
            motivation_score * 0.2 +
            career_score * 0.2 +
            personal_score * 0.15 +
            utilization_score * 0.15
        ) + variation
        
        return max(0, min(100, round(total_score, 1)))  # Ensure 0-100 range


# Additional helper view for getting employee criticality summary
class EmployeeCriticalitySummaryAPIView(APIView):
    """
    Get a comprehensive criticality summary for an employee
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get comprehensive criticality summary"""
        try:
            user = request.user
            
            # Get employee profile with existing serializer
            try:
                employee_profile = EmployeeProfile.objects.get(user=user)
                profile_data = EmployeeProfileSerializer(employee_profile).data
            except EmployeeProfile.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Employee profile not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Get active project allocations with existing serializer
            active_allocations = user.employee_allocations.filter(is_active=True)
            allocation_data = ProjectAllocationSerializer(active_allocations, many=True).data
            
            # Calculate summary metrics
            total_utilization = sum(alloc.allocation_percentage for alloc in active_allocations)
            high_risk_projects = active_allocations.filter(criticality='High').count()
            
            summary = {
                'profile': profile_data,
                'allocations': allocation_data,
                'summary_metrics': {
                    'total_utilization': round(total_utilization, 1),
                    'high_risk_projects': high_risk_projects,
                    'total_active_projects': active_allocations.count(),
                    'suggested_risk': employee_profile.suggested_risk
                }
            }
            
            return Response({
                'success': True,
                'data': summary
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)