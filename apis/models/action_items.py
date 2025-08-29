from django.db import models
from django.contrib.auth.models import User


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
