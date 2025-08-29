from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator

class ActionItem(models.Model):
    id = models.AutoField(primary_key=True)
    assigned_to = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=[('Pending', 'Pending'), ('Completed', 'Completed')])
    action = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"ActionItem for {self.assigned_to.username}"

    class Meta:
        unique_together = ('assigned_to', 'title')

class Project(models.Model):
    CRITICALITY_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low')
    ]
    
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    start_date = models.DateField()
    go_live_date = models.DateField()
    status = models.CharField(max_length=20, choices=[('Active', 'Active'), ('Inactive', 'Inactive')])
    criticality = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    source = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_to = models.ManyToManyField(User, related_name='projects')

    def __str__(self):
        return f"Project {self.title}"

class CourseCategory(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=25, unique=True)
    description = models.TextField()

    def __str__(self):
        return f"CourseCategory {self.name}"

class Course(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.TextField(unique=True)
    description = models.TextField()
    source = models.URLField()
    category = models.ManyToManyField(CourseCategory)

    def __str__(self):
        return f"Course {self.title}"


class EmployeeProfile(models.Model):
    RISK_CHOICES = [
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low')
    ]
    
    TRIGGER_CHOICES = [
        ('MH', 'Mental Health'),
        ('MT', 'Motivation Factor'),
        ('CO', 'Career Opportunities'),
        ('PR', 'Personal Reason')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='team_members', help_text="Direct manager of this employee")
    profile_pic = models.URLField(blank=True, null=True)
    age = models.PositiveIntegerField(validators=[MinValueValidator(18), MaxValueValidator(100)])
    
    # Risk factors
    mental_health = models.CharField(max_length=10, choices=RISK_CHOICES, default='Medium')
    motivation_factor = models.CharField(max_length=10, choices=RISK_CHOICES, default='Medium')
    career_opportunities = models.CharField(max_length=10, choices=RISK_CHOICES, default='Medium')
    personal_reason = models.CharField(max_length=10, choices=RISK_CHOICES, default='Medium')
    
    # Manager assessment
    manager_assessment_risk = models.CharField(max_length=10, choices=RISK_CHOICES, default='Medium')
    
    # Triggers - stored as comma-separated values for multiple selection
    all_triggers = models.CharField(max_length=100, blank=True, help_text="Comma-separated trigger codes")
    primary_trigger = models.CharField(max_length=2, choices=TRIGGER_CHOICES, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def suggested_risk(self):
        """Calculate average risk from MH, MT, CO, PR"""
        risk_values = {'High': 3, 'Medium': 2, 'Low': 1}
        scores = [
            risk_values.get(self.mental_health, 2),
            risk_values.get(self.motivation_factor, 2),
            risk_values.get(self.career_opportunities, 2),
            risk_values.get(self.personal_reason, 2)
        ]
        avg_score = sum(scores) / len(scores)
        
        if avg_score >= 2.5:
            return 'High'
        elif avg_score >= 1.5:
            return 'Medium'
        else:
            return 'Low'
    
    @property
    def is_manager(self):
        """Check if this user is a manager (has team members reporting to them)"""
        return EmployeeProfile.objects.filter(manager=self.user).exists()
    
    @property
    def role(self):
        """Get user role based on whether they have team members"""
        return 'manager' if self.is_manager else 'associate'
    
    def get_team_members(self):
        """Get all team members reporting to this user"""
        if self.is_manager:
            return EmployeeProfile.objects.filter(manager=self.user).select_related('user')
        return EmployeeProfile.objects.none()
    
    def __str__(self):
        return f"Profile for {self.user.username} ({self.role})"


class ProjectAllocation(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='allocations')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='allocations')
    allocation_percentage = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Percentage of time allocated to this project"
    )
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('employee', 'project')
    
    def __str__(self):
        return f"{self.employee.username} - {self.project.title} ({self.allocation_percentage}%)"


class Survey(models.Model):
    SURVEY_TYPES = [
        ('wellness', 'Wellness Check'),
        ('feedback', 'Project Feedback'),
        ('satisfaction', 'Job Satisfaction'),
        ('skills', 'Skills Assessment'),
        ('goals', 'Goal Setting')
    ]
    
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('closed', 'Closed')
    ]
    
    title = models.CharField(max_length=200)
    description = models.TextField()
    survey_type = models.CharField(max_length=20, choices=SURVEY_TYPES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_surveys')
    target_audience = models.CharField(max_length=20, choices=[('all', 'All Employees'), ('team', 'My Team Only')], default='all')
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_anonymous = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.title} ({self.survey_type})"
    
    @property
    def response_count(self):
        return self.responses.count()
    
    @property
    def is_active(self):
        from django.utils import timezone
        now = timezone.now()
        return self.status == 'active' and self.start_date <= now <= self.end_date


class SurveyQuestion(models.Model):
    QUESTION_TYPES = [
        ('text', 'Text Response'),
        ('rating', 'Rating Scale (1-5)'),
        ('choice', 'Multiple Choice'),
        ('boolean', 'Yes/No'),
        ('scale', 'Scale (1-10)')
    ]
    
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=10, choices=QUESTION_TYPES)
    choices = models.JSONField(blank=True, null=True, help_text="For multiple choice questions")
    is_required = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.survey.title} - Q{self.order}"


class SurveyResponse(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    respondent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='survey_responses', null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('survey', 'respondent')
    
    def __str__(self):
        respondent_name = self.respondent.username if self.respondent else 'Anonymous'
        return f"{self.survey.title} - {respondent_name}"


class SurveyAnswer(models.Model):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)
    answer_rating = models.PositiveIntegerField(blank=True, null=True)
    answer_choice = models.CharField(max_length=200, blank=True, null=True)
    answer_boolean = models.BooleanField(blank=True, null=True)
    
    class Meta:
        unique_together = ('response', 'question')
    
    def __str__(self):
        return f"{self.response} - {self.question.question_text[:50]}"
    
    @property
    def answer_value(self):
        """Get the actual answer value based on question type"""
        if self.answer_text:
            return self.answer_text
        elif self.answer_rating is not None:
            return self.answer_rating
        elif self.answer_choice:
            return self.answer_choice
        elif self.answer_boolean is not None:
            return self.answer_boolean
        return None


# Import KnowledgeBase from rag module for better organization
from .models.rag import KnowledgeBase
