from django.db import models
from django.contrib.auth.models import User


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
