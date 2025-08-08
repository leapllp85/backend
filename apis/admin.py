from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    ActionItem, Project, Course, CourseCategory, EmployeeProfile, 
    ProjectAllocation, Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
)


# Inline classes for related models
class EmployeeProfileInline(admin.StackedInline):
    model = EmployeeProfile
    fk_name = 'user'  # Specify which ForeignKey to use since EmployeeProfile has multiple FKs to User
    can_delete = False
    verbose_name_plural = 'Employee Profile'
    fields = (
        'manager', 'profile_pic', 'age',
        ('mental_health', 'motivation_factor', 'career_opportunities', 'personal_reason'),
        'manager_assessment_risk', 'all_triggers', 'primary_trigger'
    )


class ProjectAllocationInline(admin.TabularInline):
    model = ProjectAllocation
    extra = 0
    fields = ('project', 'allocation_percentage', 'start_date', 'end_date', 'is_active')


class SurveyQuestionInline(admin.TabularInline):
    model = SurveyQuestion
    extra = 1
    fields = ('question_text', 'question_type', 'choices', 'is_required', 'order')
    ordering = ('order',)


class SurveyAnswerInline(admin.TabularInline):
    model = SurveyAnswer
    extra = 0
    fields = ('question', 'answer_text', 'answer_rating', 'answer_choice', 'answer_boolean')
    readonly_fields = ('question',)


# Extended User Admin
class UserAdmin(BaseUserAdmin):
    inlines = (EmployeeProfileInline, ProjectAllocationInline)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'get_role', 'get_manager')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    
    def get_role(self, obj):
        try:
            return obj.employee_profile.role
        except EmployeeProfile.DoesNotExist:
            return 'No Profile'
    get_role.short_description = 'Role'
    
    def get_manager(self, obj):
        try:
            manager = obj.employee_profile.manager
            return f"{manager.first_name} {manager.last_name}" if manager else 'No Manager'
        except EmployeeProfile.DoesNotExist:
            return 'No Profile'
    get_manager.short_description = 'Manager'


# Employee Profile Admin
@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'get_full_name', 'role', 'manager', 'age', 
        'mental_health', 'motivation_factor', 'manager_assessment_risk', 'suggested_risk'
    )
    list_filter = (
        'mental_health', 'motivation_factor', 'career_opportunities', 
        'personal_reason', 'manager_assessment_risk', 'primary_trigger'
    )
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user', 'manager')
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'manager', 'profile_pic', 'age')
        }),
        ('Risk Assessment', {
            'fields': (
                ('mental_health', 'motivation_factor'),
                ('career_opportunities', 'personal_reason'),
                'manager_assessment_risk'
            )
        }),
        ('Triggers', {
            'fields': ('all_triggers', 'primary_trigger')
        })
    )
    
    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}"
    get_full_name.short_description = 'Full Name'


# Action Item Admin
@admin.register(ActionItem)
class ActionItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'assigned_to', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at', 'updated_at')
    search_fields = ('title', 'assigned_to__username', 'assigned_to__first_name', 'assigned_to__last_name')
    raw_id_fields = ('assigned_to',)
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)


# Project Admin
@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'criticality', 'start_date', 'go_live_date', 'get_team_size')
    list_filter = ('status', 'criticality', 'start_date', 'go_live_date')
    search_fields = ('title', 'description')
    filter_horizontal = ('assigned_to',)
    date_hierarchy = 'start_date'
    fieldsets = (
        ('Project Information', {
            'fields': ('title', 'description', 'source')
        }),
        ('Timeline', {
            'fields': ('start_date', 'go_live_date')
        }),
        ('Status & Priority', {
            'fields': ('status', 'criticality')
        }),
        ('Team Assignment', {
            'fields': ('assigned_to',)
        })
    )
    
    def get_team_size(self, obj):
        return obj.assigned_to.count()
    get_team_size.short_description = 'Team Size'


# Project Allocation Admin
@admin.register(ProjectAllocation)
class ProjectAllocationAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'project', 'allocation_percentage', 
        'start_date', 'end_date', 'is_active'
    )
    list_filter = ('is_active', 'start_date', 'end_date', 'project__criticality')
    search_fields = (
        'employee__username', 'employee__first_name', 'employee__last_name',
        'project__title'
    )
    raw_id_fields = ('employee', 'project')
    date_hierarchy = 'start_date'
    ordering = ('-start_date',)


# Course Category Admin
@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'get_course_count')
    search_fields = ('name', 'description')
    
    def get_course_count(self, obj):
        return obj.course_set.count()
    get_course_count.short_description = 'Number of Courses'


# Course Admin
@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'get_categories')
    list_filter = ('category',)
    search_fields = ('title', 'description', 'category__name')
    filter_horizontal = ('category',)
    ordering = ('title',)
    
    def get_categories(self, obj):
        return ", ".join([cat.name for cat in obj.category.all()])
    get_categories.short_description = 'Categories'


# Survey Admin
@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'survey_type', 'status', 'target_audience', 
        'created_by', 'start_date', 'end_date', 'response_count', 'is_active'
    )
    list_filter = (
        'survey_type', 'status', 'target_audience', 'is_anonymous', 
        'start_date', 'end_date', 'created_at'
    )
    search_fields = ('title', 'description', 'created_by__username')
    raw_id_fields = ('created_by',)
    date_hierarchy = 'start_date'
    inlines = [SurveyQuestionInline]
    fieldsets = (
        ('Survey Information', {
            'fields': ('title', 'description', 'survey_type')
        }),
        ('Configuration', {
            'fields': ('status', 'target_audience', 'is_anonymous', 'created_by')
        }),
        ('Schedule', {
            'fields': ('start_date', 'end_date')
        })
    )


# Survey Question Admin
@admin.register(SurveyQuestion)
class SurveyQuestionAdmin(admin.ModelAdmin):
    list_display = ('survey', 'question_text', 'question_type', 'is_required', 'order')
    list_filter = ('question_type', 'is_required', 'survey__survey_type')
    search_fields = ('question_text', 'survey__title')
    raw_id_fields = ('survey',)
    ordering = ('survey', 'order')


# Survey Response Admin
@admin.register(SurveyResponse)
class SurveyResponseAdmin(admin.ModelAdmin):
    list_display = ('survey', 'respondent', 'is_completed', 'submitted_at')
    list_filter = ('is_completed', 'submitted_at', 'survey__survey_type')
    search_fields = ('survey__title', 'respondent__username')
    raw_id_fields = ('survey', 'respondent')
    date_hierarchy = 'submitted_at'
    inlines = [SurveyAnswerInline]
    readonly_fields = ('submitted_at',)


# Survey Answer Admin
@admin.register(SurveyAnswer)
class SurveyAnswerAdmin(admin.ModelAdmin):
    list_display = ('response', 'question', 'get_answer_value')
    list_filter = ('question__question_type', 'response__survey__survey_type')
    search_fields = ('response__survey__title', 'question__question_text')
    raw_id_fields = ('response', 'question')
    
    def get_answer_value(self, obj):
        return obj.answer_value
    get_answer_value.short_description = 'Answer'


# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)

# Customize admin site headers
admin.site.site_header = 'Corporate MVP Administration'
admin.site.site_title = 'Corporate MVP Admin'
admin.site.index_title = 'Welcome to Corporate MVP Administration'
