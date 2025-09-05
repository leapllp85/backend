from django.db import models
from django.contrib.auth.models import User
from apis.models import Project
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Count, Sum

CRITICALITY_MAP = {
    "High": 3,
    "Medium": 2,
    "Low": 1
}
CRITICALITY_SCORE_MAP = {
    3: "High",
    2: "Medium",
    1: "Low"
}

CRITICALITY_CHOICES = [
    ('High', 'High'),
    ('Medium', 'Medium'),
    ('Low', 'Low')
]

class EmployeeProfile(models.Model):
    TRIGGER_CHOICES = [
        ('MH', 'Mental Health'),
        ('MT', 'Motivation Factor'),
        ('CO', 'Career Opportunities'),
        ('PR', 'Personal Reason')
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    manager = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, 
                               related_name='team_members', 
                               help_text="Direct manager of this employee")
    profile_pic = models.URLField(blank=True, null=True)
    age = models.PositiveIntegerField(validators=[MinValueValidator(18), MaxValueValidator(100)])
    
    # Risk assessment fields
    mental_health = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    motivation_factor = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    career_opportunities = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    personal_reason = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    manager_assessment_risk = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    
    # Trigger fields
    all_triggers = models.CharField(max_length=100, blank=True, 
                                   help_text="Comma-separated trigger codes")
    primary_trigger = models.CharField(max_length=2, choices=TRIGGER_CHOICES, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"EmployeeProfile for {self.user.username}"

    def mental_health_score(self):
        return CRITICALITY_MAP.get(self.mental_health, 2)
    
    def motivation_factor_score(self):
        return CRITICALITY_MAP.get(self.motivation_factor, 2)
    
    def career_opportunities_score(self):
        return CRITICALITY_MAP.get(self.career_opportunities, 2)
    
    def personal_reason_score(self):
        return CRITICALITY_MAP.get(self.personal_reason, 2)

    @property
    def suggested_risk(self):
        """Calculate average risk from MH, MT, CO, PR"""
        risk_values = CRITICALITY_MAP
        
        risks = [
            self.mental_health,
            self.motivation_factor,
            self.career_opportunities,
            self.personal_reason
        ]
        
        total = sum(risk_values.get(risk, 2) for risk in risks)
        average = total / len(risks)
        
        if average >= 2.5:
            return 'High'
        elif average >= 1.5:
            return 'Medium'
        else:
            return 'Low'

    @property
    def is_manager(self):
        """Check if this user is a manager (has team members reporting to them)"""
        return self.user.team_members.exists()

    @property
    def role(self):
        """Get user role based on whether they have team members"""
        return 'Manager' if self.is_manager else 'Associate'

    @property
    def manager_name(self):
        """Get manager's full name"""
        if self.manager:
            return f"{self.manager.first_name} {self.manager.last_name}".strip() or self.manager.username
        return None

    def get_team_members(self):
        """Get all team members reporting to this user"""
        return EmployeeProfile.objects.filter(manager=self.user)

    @property
    def employee_project_criticality(self):
        """Get employee criticality"""
        project_allocations = ProjectAllocation.objects.filter(employee=self.user).values('criticality').annotate(count=Count('criticality'))
        criticality_values = [allocation['count'] * CRITICALITY_MAP.get(allocation['criticality'], 2) for allocation in project_allocations]
        total = sum(criticality_values)
        average = total / len(criticality_values)
        
        if average >= 2.5:
            return 'High'
        elif average >= 1.5:
            return 'Medium'
        else:
            return 'Low'

    @property
    def team_count(self):
        return self.user.team_members.count()

    @property
    def total_allocation(self):
        return self.user.employee_allocations.aggregate(total=Sum('allocation_percentage'))['total']

    @property
    def project_criticality(self):
        return self.user.employee_allocations.aggregate(total=Sum('allocation_percentage'))['total']
        


class ProjectAllocation(models.Model):
    employee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='employee_allocations')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='project_allocations')
    criticality = models.CharField(max_length=10, choices=CRITICALITY_CHOICES, default='Medium')
    allocation_percentage = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
        help_text="Percentage of time allocated to this project"
    )
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.employee.username} - {self.project.title} ({self.allocation_percentage}%)"

    class Meta:
        unique_together = ('employee', 'project')
