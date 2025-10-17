from apis.models.employees import CRITICALITY_SCORE_MAP
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from apis.permissions import IsManager
from apis.serializers import CriticalityVsRiskSerializer, RiskDistributionSerializer
from apis.models import EmployeeProfile, Attrition
from rest_framework import status
from django.db.models import Avg, Count, Q, Sum, Case, When, IntegerField, F
from django.utils import timezone
from datetime import datetime, timedelta
import hashlib
from ..models import EmployeeProfile, ProjectAllocation
from ..serializers import (
    CriticalityMetricsSerializer,
    CriticalityTrendSerializer,
    CriticalityTrendsInputSerializer,
    EmployeeProfileSerializer,
    ProjectAllocationSerializer,
    AttritionSerializer
)
from apis.models.employees import Trigger, PRIMARY_TRIGGER_CHOICES



class CriticalityVsRiskView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        user_id = request.user.id
        
        # Optimized query with select_related and database aggregations
        employee_profiles = EmployeeProfile.objects.filter(
            manager=user_id
        )
        # .select_related('user')
        # .annotate(
        #     mental_health_numeric=Case(
        #         When(mental_health='High', then=3),
        #         When(mental_health='Medium', then=2),
        #         When(mental_health='Low', then=1),
        #         default=2,
        #         output_field=IntegerField()
        #     ),
        #     career_opportunities_numeric=Case(
        #         When(career_opportunities='High', then=3),
        #         When(career_opportunities='Medium', then=2),
        #         When(career_opportunities='Low', then=1),
        #         default=2,
        #         output_field=IntegerField()
        #     )
        # )
        
        # Single aggregation query for averages
        # aggregated_data = employee_profiles.aggregate(
        #     avg_mental_health=Avg('mental_health_numeric'),
        #     avg_career_growth=Avg('career_opportunities_numeric'),
        #     total_count=Count('id')
        # )
        
        # Build scatter data efficiently
        # scatter_data = [{
        #     "criticality": profile.employee_project_criticality,
        #     "risk": profile.suggested_risk,
        #     "employee_name": f"{profile.user.first_name} {profile.user.last_name}"
        # } for profile in employee_profiles]
        graph_data_queryset = (
            employee_profiles
            .values(
                'employee_project_criticality',
                'manager_assessment_risk'
            )
            .annotate(
                value=Count('id')
            )
        )

        # Format data for your chart
        graph_data = [
            {
                "label": f"Criticality: {row['employee_project_criticality']}, Risk: {row['manager_assessment_risk']}",
                "value": row['value']
            }
            for row in graph_data_queryset
        ]

        
        # Calculate averages from aggregated data
        # avg_mental_health = int(aggregated_data['avg_mental_health'] or 2)
        # avg_career_growth = int(aggregated_data['avg_career_growth'] or 2)
        
        data = {
            # "work_wellness": CRITICALITY_SCORE_MAP.get(avg_mental_health, "Medium"),
            # "career_growth": CRITICALITY_SCORE_MAP.get(avg_career_growth, "Medium"),
            "graph_data": graph_data,
        }
        
        # serializer = CriticalityVsRiskSerializer(data)
        return Response({"success": True, "data": data, "message": "Risk analysis retrieved successfully"})


class RiskDistributionView(APIView):
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request):
        user_id = request.user.id
        
        # Single aggregation query for all risk distribution metrics
        risk_stats = EmployeeProfile.objects.filter(manager=user_id).aggregate(
            # Mental Health distribution
            mental_health_high=Count('id', filter=Q(mental_health='High')),
            mental_health_medium=Count('id', filter=Q(mental_health='Medium')),
            mental_health_low=Count('id', filter=Q(mental_health='Low')),
            
            # Motivation distribution
            motivation_high=Count('id', filter=Q(motivation_factor='High')),
            motivation_medium=Count('id', filter=Q(motivation_factor='Medium')),
            motivation_low=Count('id', filter=Q(motivation_factor='Low')),
            
            # Career opportunities distribution
            career_high=Count('id', filter=Q(career_opportunities='High')),
            career_medium=Count('id', filter=Q(career_opportunities='Medium')),
            career_low=Count('id', filter=Q(career_opportunities='Low')),
            
            # Personal factors distribution
            personal_high=Count('id', filter=Q(personal_reason='High')),
            personal_medium=Count('id', filter=Q(personal_reason='Medium')),
            personal_low=Count('id', filter=Q(personal_reason='Low'))
        )
        
        data = {
            "mental_health": {
                "high": risk_stats['mental_health_high'],
                "medium": risk_stats['mental_health_medium'],
                "low": risk_stats['mental_health_low']
            },
            "motivation": {
                "high": risk_stats['motivation_high'],
                "medium": risk_stats['motivation_medium'],
                "low": risk_stats['motivation_low']
            },
            "career_opportunities": {
                "high": risk_stats['career_high'],
                "medium": risk_stats['career_medium'],
                "low": risk_stats['career_low']
            },
            "personal_factors": {
                "high": risk_stats['personal_high'],
                "medium": risk_stats['personal_medium'],
                "low": risk_stats['personal_low']
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
            mental_health = self._calculate_mental_health_score(employee_profile)
            attrition_risk = self._calculate_attrition_risk_score(employee_profile)
            
            # Calculate project health score
            project_health = self._calculate_project_health(user)
            
            # Prepare data for serialization
            metrics_data = {
                'mental_health': mental_health,
                'attrition_risk': attrition_risk,
                'project_health': project_health
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
    
    def _calculate_mental_health_score(self, employee_profile):
        """
        Calculate mental health score as percentage (0-100)
        Higher score means better mental health
        """
        # Convert text risk level to score (inverted - lower risk = higher score)
        risk_scores = {'High': 25, 'Medium': 50, 'Low': 75}
        base_score = risk_scores.get(employee_profile.mental_health, 50)
        
        # Consider other related factors for a more comprehensive score
        motivation_score = risk_scores.get(employee_profile.motivation_factor, 50)
        career_score = risk_scores.get(employee_profile.career_opportunities, 50)
        personal_score = risk_scores.get(employee_profile.personal_reason, 50)
        
        # Weighted calculation with mental health as primary factor
        total_score = (
            base_score * 0.5 +  # Mental health is 50% of the score
            motivation_score * 0.2 +
            career_score * 0.2 +
            personal_score * 0.1
        )
        
        return round(max(0, min(100, total_score)), 1)
    
    def _calculate_attrition_risk_score(self, employee_profile):
        """
        Calculate attrition risk score as percentage (0-100)
        Higher score means lower attrition risk (better retention)
        """
        # Convert suggested risk to score (inverted - lower risk = higher score)
        risk_scores = {'High': 20, 'Medium': 50, 'Low': 80}
        base_score = risk_scores.get(employee_profile.suggested_risk, 50)
        
        # Consider manager assessment as additional factor
        manager_score = risk_scores.get(employee_profile.manager_assessment_risk, 50)
        
        # Consider other risk factors
        mental_health_score = risk_scores.get(employee_profile.mental_health, 50)
        motivation_score = risk_scores.get(employee_profile.motivation_factor, 50)
        career_score = risk_scores.get(employee_profile.career_opportunities, 50)
        
        # Weighted calculation with suggested risk as primary factor
        total_score = (
            base_score * 0.4 +  # Suggested risk is 40% of the score
            manager_score * 0.3 +  # Manager assessment is 30%
            mental_health_score * 0.1 +
            motivation_score * 0.1 +
            career_score * 0.1
        )
        
        return round(max(0, min(100, total_score)), 1)
    
    def _calculate_project_health(self, user):
        """
        Calculate project health score based on project factors
        Higher score means better project health
        """
        from django.utils import timezone
        from datetime import timedelta
        
        # Get user's active project allocations
        active_allocations = user.employee_allocations.filter(is_active=True)
        
        if not active_allocations.exists():
            return 75.0  # Neutral score if no active projects
        
        total_health_score = 0
        total_weight = 0
        
        for allocation in active_allocations:
            project = allocation.project
            weight = allocation.allocation_percentage / 100.0  # Convert to 0-1 scale
            
            # Project criticality score (inverted - lower criticality = better health)
            criticality_scores = {'High': 30, 'Medium': 60, 'Low': 90}
            criticality_score = criticality_scores.get(allocation.criticality, 60)
            
            # Project timeline health (based on time remaining vs total duration)
            timeline_score = 75  # Default neutral score
            if allocation.end_date:
                today = timezone.now().date()
                if allocation.end_date >= today:
                    total_duration = (allocation.end_date - allocation.start_date).days
                    remaining_days = (allocation.end_date - today).days
                    
                    if total_duration > 0:
                        progress_ratio = 1 - (remaining_days / total_duration)
                        # Better score for projects that are on track (30-80% complete)
                        if 0.3 <= progress_ratio <= 0.8:
                            timeline_score = 85
                        elif 0.1 <= progress_ratio < 0.3 or 0.8 < progress_ratio <= 0.95:
                            timeline_score = 70
                        elif progress_ratio > 0.95:
                            timeline_score = 50  # Overdue or very close to deadline
                        else:
                            timeline_score = 60  # Just started
                else:
                    timeline_score = 40  # Overdue
            
            # Project status score
            status_score = 80 if project.status == 'Active' else 40
            
            # Allocation health (optimal allocation around 60-80%)
            allocation_health = 75  # Default
            if 60 <= allocation.allocation_percentage <= 80:
                allocation_health = 85
            elif 40 <= allocation.allocation_percentage < 60 or 80 < allocation.allocation_percentage <= 100:
                allocation_health = 70
            elif allocation.allocation_percentage < 40:
                allocation_health = 60
            else:  # > 100%
                allocation_health = 45
            
            # Weighted project health score
            project_health = (
                criticality_score * 0.3 +
                timeline_score * 0.3 +
                status_score * 0.2 +
                allocation_health * 0.2
            )
            
            total_health_score += project_health * weight
            total_weight += weight
        
        # Calculate weighted average
        if total_weight > 0:
            final_score = total_health_score / total_weight
        else:
            final_score = 75.0
        
        return round(max(0, min(100, final_score)), 1)


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


class AttritionTrendsAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        user = request.user
        # m: months, y: years
        span = request.query_params.get('span', '3m')
        print(timezone.now().month - int(span.replace('m', '')))
        print(user.username)
        
        if 'm' in span:
            attrition_data = Attrition.objects.filter(manager__username=user.username, month__gte=timezone.now().month - int(span.replace('m', '')))
        elif 'y' in span:
            attrition_data = Attrition.objects.filter(manager__username=user.username, year__gte=timezone.now().year - int(span.replace('y', '')))
        
        # Serialize the attrition data for line graph
        serializer = AttritionSerializer(attrition_data, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        }, status=status.HTTP_200_OK)

class PrimaryTriggerAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        user = request.user
        res = {}
        for primary_trigger in PRIMARY_TRIGGER_CHOICES:
            res[primary_trigger[0]] = EmployeeProfile.objects.filter(manager=user, primary_trigger=primary_trigger[0]).count()
        return Response({
            'success': True,
            'data': res
        }, status=status.HTTP_200_OK)

class AllTriggerAPIView(APIView):
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        user = request.user
        res = {}
        for trigger in Trigger.objects.values_list('name', flat=True).distinct():
            res[trigger] = EmployeeProfile.objects.filter(manager=user, all_triggers__name=trigger).count()
        return Response({
            'success': True,
            'data': res
        }, status=status.HTTP_200_OK)