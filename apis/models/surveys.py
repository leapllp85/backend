from django.db import models
from django.contrib.auth.models import User


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
    target_audience = models.CharField(
        max_length=20, 
        choices=[
            ('all', 'All Employees'), 
            ('team', 'My Team Only'),
            ('department', 'By Department'),
            ('role', 'By Role'),
            ('risk_level', 'By Risk Level'),
            ('custom', 'Custom Selection')
        ], 
        default='all'
    )
    
    # Additional targeting fields
    target_departments = models.JSONField(
        blank=True, null=True,
        help_text="List of department names for department targeting"
    )
    target_roles = models.JSONField(
        blank=True, null=True,
        help_text="List of roles: ['manager', 'associate'] for role targeting"
    )
    target_risk_levels = models.JSONField(
        blank=True, null=True,
        help_text="List of risk levels: ['High', 'Medium', 'Low'] for risk targeting"
    )
    target_employees = models.ManyToManyField(
        User, blank=True,
        related_name='targeted_surveys',
        help_text="Specific employees for custom targeting"
    )
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_anonymous = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Survey: {self.title}"

    @property
    def response_count(self):
        """Get total number of responses for this survey"""
        return self.responses.count()

    @property
    def is_active(self):
        """Check if survey is currently active"""
        from django.utils import timezone
        now = timezone.now()
        return (self.status == 'active' and 
                self.start_date <= now <= self.end_date)
    
    @property
    def is_viewable(self):
        """Check if survey can be viewed (includes expired surveys)"""
        return self.status in ['active', 'closed']
    
    @property
    def can_accept_responses(self):
        """Check if survey can accept new responses"""
        return self.is_active
    
    def get_target_employees(self):
        """Get list of employees based on targeting criteria"""
        from .employees import EmployeeProfile
        
        if self.target_audience == 'all':
            return User.objects.filter(employee_profile__isnull=False)
        
        elif self.target_audience == 'team':
            return User.objects.filter(employee_profile__manager=self.created_by)
        
        elif self.target_audience == 'department':
            # Assuming department is stored in a field - adjust as needed
            if self.target_departments:
                return User.objects.filter(
                    employee_profile__department__in=self.target_departments
                )
        
        elif self.target_audience == 'role':
            if self.target_roles:
                if 'manager' in self.target_roles and 'associate' in self.target_roles:
                    return User.objects.filter(employee_profile__isnull=False)
                elif 'manager' in self.target_roles:
                    return User.objects.filter(employee_profile__is_manager=True)
                elif 'associate' in self.target_roles:
                    return User.objects.filter(employee_profile__is_manager=False)
        
        elif self.target_audience == 'risk_level':
            if self.target_risk_levels:
                return User.objects.filter(
                    employee_profile__suggested_risk__in=self.target_risk_levels
                )
        
        elif self.target_audience == 'custom':
            return self.target_employees.all()
        
        return User.objects.none()


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

    def __str__(self):
        return f"{self.survey.title} - Q{self.order}: {self.question_text[:50]}"

    class Meta:
        ordering = ['order']


class SurveyResponse(models.Model):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE, related_name='responses')
    respondent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='survey_responses', 
                                  null=True, blank=True)
    is_completed = models.BooleanField(default=False)
    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        respondent_name = self.respondent.username if self.respondent else "Anonymous"
        return f"{self.survey.title} - Response by {respondent_name}"

    class Meta:
        unique_together = ('survey', 'respondent')


class SurveyAnswer(models.Model):
    response = models.ForeignKey(SurveyResponse, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(SurveyQuestion, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)
    answer_rating = models.PositiveIntegerField(blank=True, null=True)
    answer_choice = models.CharField(max_length=200, blank=True, null=True)
    answer_boolean = models.BooleanField(blank=True, null=True)

    def __str__(self):
        return f"{self.response} - {self.question.question_text[:50]}"

    class Meta:
        unique_together = ('response', 'question')

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
