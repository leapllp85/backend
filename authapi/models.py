from django.db import models
from django.contrib.auth.models import User

class EmployeeDesignation(models.Model):
    name = models.CharField(max_length=50, primary_key=True)

    def __str__(self):
        return self.name

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    phone_number = models.CharField(max_length=20, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    employee_designation = models.ForeignKey(EmployeeDesignation, to_field='name', on_delete=models.SET_NULL, null=True, blank=True)
    supervisor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates')
    gender = models.CharField(max_length=1, choices=[('M', 'Male'), ('F', 'Female')]) # New field
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return f"Profile for {self.user.username}"

