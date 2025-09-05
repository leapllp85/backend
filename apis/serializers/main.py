from rest_framework import serializers
from ..models import ActionItem, Project, Course, CourseCategory, EmployeeProfile, ProjectAllocation, Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
from django.contrib.auth.models import User

class ActionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionItem
        fields = '__all__'

class AssignedUserSerializer(serializers.ModelSerializer):
    """Serializer for users assigned to projects with profile information"""
    full_name = serializers.SerializerMethodField()
    profile_pic = serializers.CharField(source='employee_profile.profile_pic', read_only=True)
    role = serializers.CharField(source='employee_profile.role', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'email', 'profile_pic', 'role']
    
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username


class ProjectSerializer(serializers.ModelSerializer):
    assigned_to = AssignedUserSerializer(many=True, read_only=True)
    team_size = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'title', 'description', 'start_date', 'go_live_date', 
            'status', 'criticality', 'source', 'created_at', 'assigned_to', 'team_size'
        ]
    
    def get_team_size(self, obj):
        return obj.assigned_to.count()

class CourseSerializer(serializers.ModelSerializer):
    category_names = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'source', 'category_names']
    
    def get_category_names(self, obj):
        """Return list of category names"""
        return [category.name for category in obj.category.all()]

class CourseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseCategory
        fields = '__all__'


class EmployeeProfileSerializer(serializers.ModelSerializer):
    suggested_risk = serializers.ReadOnlyField()
    username = serializers.CharField(source='user.username', read_only=True)
    first_name = serializers.CharField(source='user.first_name', read_only=True)
    last_name = serializers.CharField(source='user.last_name', read_only=True)
    email = serializers.CharField(source='user.email', read_only=True)
    role = serializers.CharField(source='user.employee_profile.role', read_only=True)
    is_manager = serializers.BooleanField(source='user.employee_profile.is_manager', read_only=True)
    manager_name = serializers.CharField(source='user.employee_profile.manager_name', read_only=True)
    team_count = serializers.IntegerField(source='user.employee_profile.team_count', read_only=True)
    project_criticality = serializers.CharField(source='user.employee_profile.project_criticality', read_only=True)
    total_allocation = serializers.IntegerField(source='user.employee_profile.total_allocation', read_only=True)
    
    class Meta:
        model = EmployeeProfile
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 
            'mental_health', 'motivation_factor', 'career_opportunities', 
            'personal_reason', 'suggested_risk', 'manager_assessment_risk',
            'all_triggers', 'primary_trigger', 'age', 'profile_pic',
            'role', 'is_manager', 'manager_name', 'team_count',
            'project_criticality', 'total_allocation'
        ]


class ProjectAllocationSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.username', read_only=True)
    project_name = serializers.CharField(source='project.title', read_only=True)
    project_criticality = serializers.CharField(source='project.criticality', read_only=True)
    
    class Meta:
        model = ProjectAllocation
        fields = [
            'id', 'employee_name', 'project_name', 'project_criticality',
            'allocation_percentage', 'start_date', 'end_date', 'is_active'
        ]


class TeamMemberDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for team member with all required fields for My Team view"""
    profile_pic = serializers.CharField(source='employee_profile.profile_pic', read_only=True)
    mental_health = serializers.CharField(source='employee_profile.mental_health', read_only=True)
    motivation_factor = serializers.CharField(source='employee_profile.motivation_factor', read_only=True)
    career_opportunities = serializers.CharField(source='employee_profile.career_opportunities', read_only=True)
    personal_reason = serializers.CharField(source='employee_profile.personal_reason', read_only=True)
    suggested_risk = serializers.CharField(source='employee_profile.suggested_risk', read_only=True)
    manager_assessment_risk = serializers.CharField(source='employee_profile.manager_assessment_risk', read_only=True)
    all_triggers = serializers.CharField(source='employee_profile.all_triggers', read_only=True)
    primary_trigger = serializers.CharField(source='employee_profile.primary_trigger', read_only=True)
    age = serializers.IntegerField(source='employee_profile.age', read_only=True)
    email = serializers.SerializerMethodField()
    
    def get_email(self, obj):
        return obj.email
    
    # Project criticality from current allocations
    project_criticality = serializers.SerializerMethodField()
    total_allocation = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'profile_pic', 
                 'mental_health', 'motivation_factor', 'career_opportunities', 
                 'personal_reason', 'suggested_risk', 'project_criticality',
                 'manager_assessment_risk', 'all_triggers', 'primary_trigger',
                 'age', 'email', 'total_allocation']
    
    def get_project_criticality(self, obj):
        """Get highest criticality from active project allocations"""
        active_allocations = obj.employee_allocations.filter(is_active=True)
        if not active_allocations.exists():
            return 'Low'
        
        criticalities = [alloc.project.criticality for alloc in active_allocations]
        if 'High' in criticalities:
            return 'High'
        elif 'Medium' in criticalities:
            return 'Medium'
        return 'Low'
    
    def get_total_allocation(self, obj):
        """Get total allocation percentage across all active projects"""
        active_allocations = obj.employee_allocations.filter(is_active=True)
        return sum(alloc.allocation_percentage for alloc in active_allocations)


class SurveyQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyQuestion
        fields = '__all__'


class SurveySerializer(serializers.ModelSerializer):
    questions = SurveyQuestionSerializer(many=True, read_only=True)
    response_count = serializers.ReadOnlyField()
    is_active = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    class Meta:
        model = Survey
        fields = '__all__'


class SurveyAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_type = serializers.CharField(source='question.question_type', read_only=True)
    answer_value = serializers.ReadOnlyField()
    
    class Meta:
        model = SurveyAnswer
        fields = '__all__'


class SurveyResponseSerializer(serializers.ModelSerializer):
    answers = SurveyAnswerSerializer(many=True, read_only=True)
    survey_title = serializers.CharField(source='survey.title', read_only=True)
    respondent_name = serializers.CharField(source='respondent.get_full_name', read_only=True)
    
    class Meta:
        model = SurveyResponse
        fields = '__all__'


class UserRoleSerializer(serializers.ModelSerializer):
    """Serializer for user with role information"""
    role = serializers.CharField(source='employee_profile.role', read_only=True)
    is_manager = serializers.BooleanField(source='employee_profile.is_manager', read_only=True)
    manager_name = serializers.SerializerMethodField()
    team_count = serializers.SerializerMethodField()
    profile_pic = serializers.CharField(source='employee_profile.profile_pic', read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 
                 'role', 'is_manager', 'manager_name', 'team_count', 'profile_pic']
    
    def get_manager_name(self, obj):
        try:
            if obj.employee_profile.manager:
                return f"{obj.employee_profile.manager.first_name} {obj.employee_profile.manager.last_name}"
        except:
            pass
        return None
    
    def get_team_count(self, obj):
        try:
            if obj.employee_profile.is_manager:
                return obj.employee_profile.get_team_members().count()
        except:
            pass
        return 0


class MyProjectsSerializer(serializers.ModelSerializer):
    """Serializer for user's project allocations"""
    allocation_percentage = serializers.SerializerMethodField()
    project_status = serializers.CharField(source='status', read_only=True)
    project_criticality = serializers.CharField(source='criticality', read_only=True)
    
    class Meta:
        model = Project
        fields = ['id', 'title', 'description', 'start_date', 'go_live_date', 
                 'project_status', 'project_criticality', 'allocation_percentage']
    
    def get_allocation_percentage(self, obj):
        user = self.context.get('user')
        if user:
            allocation = ProjectAllocation.objects.filter(project=obj, employee=user, is_active=True).first()
            return allocation.allocation_percentage if allocation else 0
        return 0
