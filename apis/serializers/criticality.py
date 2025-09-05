from rest_framework import serializers
from ..models.employees import CRITICALITY_CHOICES
from ..serializers.main import EmployeeProfileSerializer
from ..serializers.main import ProjectAllocationSerializer

class CriticalityVsRiskSerializer(serializers.Serializer):
    scatter_data = serializers.ListField(child=serializers.DictField())
    work_wellness = serializers.CharField()
    career_growth = serializers.CharField()

class RiskDistributionSerializer(serializers.Serializer):
    mental_health = serializers.DictField(child=serializers.IntegerField())
    motivation = serializers.DictField(child=serializers.IntegerField())
    career_opportunities = serializers.DictField(child=serializers.IntegerField())
    personal_factors = serializers.DictField(child=serializers.IntegerField())

class CriticalityMetricsSerializer(serializers.Serializer):
    """Serializer for criticality metrics response"""
    mental_health_risk = serializers.ChoiceField(
        choices=CRITICALITY_CHOICES,
        help_text="Mental health risk level"
    )
    attrition_risk = serializers.ChoiceField(
        choices=CRITICALITY_CHOICES,
        help_text="Attrition risk level"
    )
    projects_at_risk = serializers.IntegerField(
        min_value=0,
        help_text="Number of high-criticality projects"
    )
    avg_utilization = serializers.FloatField(
        min_value=0.0,
        max_value=200.0,  # Allow for over-allocation scenarios
        help_text="Average utilization percentage"
    )
    overall_score = serializers.FloatField(
        min_value=0.0,
        max_value=100.0,
        help_text="Overall criticality score"
    )
    last_updated = serializers.DateTimeField(
        help_text="Last update timestamp"
    )

    def validate_overall_score(self, value):
        """Validate overall score is within valid range"""
        if value < 0 or value > 100:
            raise serializers.ValidationError("Overall score must be between 0 and 100")
        return round(value, 1)

    def validate_avg_utilization(self, value):
        """Validate utilization is within reasonable bounds"""
        if value < 0:
            raise serializers.ValidationError("Utilization cannot be negative")
        return round(value, 1)


class CriticalityTrendSerializer(serializers.Serializer):
    """Serializer for individual trend data points"""
    date = serializers.DateField(
        help_text="Date for this trend point"
    )
    overall_score = serializers.FloatField(
        min_value=0.0,
        max_value=100.0,
        help_text="Overall score for this date"
    )
    mental_health = serializers.FloatField(
        min_value=0.0,
        max_value=100.0,
        help_text="Mental health score for this date"
    )
    attrition_risk = serializers.FloatField(
        min_value=0.0,
        max_value=100.0,
        help_text="Attrition risk score for this date"
    )
    utilization = serializers.FloatField(
        min_value=0.0,
        max_value=200.0,  # Allow for over-allocation
        help_text="Utilization percentage for this date"
    )

    def validate_overall_score(self, value):
        return round(max(0, min(100, value)), 1)

    def validate_mental_health(self, value):
        return round(max(0, min(100, value)), 1)

    def validate_attrition_risk(self, value):
        return round(max(0, min(100, value)), 1)

    def validate_utilization(self, value):
        return round(max(0, value), 1)


class CriticalityTrendsInputSerializer(serializers.Serializer):
    """Serializer for validating trends request parameters"""
    days = serializers.IntegerField(
        default=30,
        min_value=1,
        max_value=365,
        help_text="Number of days to retrieve trends for"
    )

    def validate_days(self, value):
        if value < 1 or value > 365:
            raise serializers.ValidationError("Days must be between 1 and 365")
        return value


# Standard response wrappers
class CriticalityMetricsResponseSerializer(serializers.Serializer):
    """Serializer for the complete metrics response"""
    success = serializers.BooleanField(default=True)
    data = CriticalityMetricsSerializer()
    message = serializers.CharField(required=False, allow_blank=True)


class CriticalityTrendsResponseSerializer(serializers.Serializer):
    """Serializer for the complete trends response"""
    success = serializers.BooleanField(default=True)
    data = CriticalityTrendSerializer(many=True)
    message = serializers.CharField(required=False, allow_blank=True)


class ErrorResponseSerializer(serializers.Serializer):
    """Serializer for error responses"""
    success = serializers.BooleanField(default=False)
    message = serializers.CharField()
    errors = serializers.DictField(required=False)


# Extended serializers for criticality-specific data
class CriticalityEmployeeProfileSerializer(EmployeeProfileSerializer):
    """Extended employee profile serializer with criticality-specific fields"""
    overall_score = serializers.SerializerMethodField()
    current_utilization = serializers.SerializerMethodField()
    high_risk_projects = serializers.SerializerMethodField()
    
    class Meta(EmployeeProfileSerializer.Meta):
        fields = EmployeeProfileSerializer.Meta.fields + [
            'overall_score', 'current_utilization', 'high_risk_projects'
        ]
    
    def get_overall_score(self, obj):
        """Calculate overall criticality score"""
        # Get current utilization
        from django.db.models import Sum
        utilization = obj.user.employee_allocations.filter(
            is_active=True
        ).aggregate(
            total=Sum('allocation_percentage')
        )['total'] or 0
        
        return self._calculate_overall_score(obj, utilization)
    
    def get_current_utilization(self, obj):
        """Get current total utilization"""
        from django.db.models import Sum
        return obj.user.employee_allocations.filter(
            is_active=True
        ).aggregate(
            total=Sum('allocation_percentage')
        )['total'] or 0
    
    def get_high_risk_projects(self, obj):
        """Get count of high-criticality projects"""
        return obj.user.employee_allocations.filter(
            is_active=True,
            criticality='High'
        ).count()
    
    def _calculate_overall_score(self, profile, utilization):
        """Calculate overall score based on risk factors"""
        risk_scores = {'High': 25, 'Medium': 50, 'Low': 75}
        
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


class CriticalityProjectAllocationSerializer(ProjectAllocationSerializer):
    """Extended project allocation serializer with criticality context"""
    risk_score = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    
    class Meta(ProjectAllocationSerializer.Meta):
        fields = ProjectAllocationSerializer.Meta.fields + [
            'risk_score', 'days_remaining'
        ]
    
    def get_risk_score(self, obj):
        """Convert criticality to numeric risk score"""
        risk_map = {'High': 3, 'Medium': 2, 'Low': 1}
        return risk_map.get(obj.criticality, 2)
    
    def get_days_remaining(self, obj):
        """Calculate days remaining in allocation"""
        if obj.end_date:
            from django.utils import timezone
            remaining = (obj.end_date - timezone.now().date()).days
            return max(0, remaining)
        return None