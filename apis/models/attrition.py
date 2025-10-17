from django.db import models
from django.contrib.auth.models import User

class Attrition(models.Model):
    manager = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attrition')
    year = models.IntegerField()
    month = models.IntegerField()
    high = models.IntegerField()
    medium = models.IntegerField()
    low = models.IntegerField()

    class Meta:
        unique_together = ('manager', 'year', 'month')
    
    def __str__(self):
        return f"{self.manager} - {self.year} - {self.month}"
        