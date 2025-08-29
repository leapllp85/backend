from django.db import models


class CourseCategory(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=25, unique=True)
    description = models.TextField()

    def __str__(self):
        return f"CourseCategory {self.name}"


class Course(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    category = models.ManyToManyField(CourseCategory, related_name='courses')

    def __str__(self):
        return f"Course {self.title}"
