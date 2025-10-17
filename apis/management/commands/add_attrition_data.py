from django.core.management.base import BaseCommand
from django.db import transaction
from apis.models import EmployeeProfile, Attrition
from django.utils import timezone
from django.db.models import Count, Q


class Command(BaseCommand):
    help = 'Collect attrition data for all EmployeeProfile records'

    def handle(self, *args, **options):
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting attrition data update process...')
        )
        
        profiles = EmployeeProfile.objects.all()
            
        with transaction.atomic():
            for profile in profiles:
                if profile.is_manager:
                    self.stdout.write(
                        self.style.SUCCESS(f'Employee {profile.user.username} (ID: {profile.id}) is a manager, adding attrition data...')
                    )
                    team_attrition_data = EmployeeProfile.objects.filter(manager=profile.user)
                    Attrition.objects.create(
                        manager=profile.user,
                        year=timezone.now().year,
                        month=timezone.now().month,
                        high=team_attrition_data.filter(manager_assessment_risk='High').count(),
                        medium=team_attrition_data.filter(manager_assessment_risk='Medium').count(),
                        low=team_attrition_data.filter(manager_assessment_risk='Low').count(),
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'Employee {profile.user.username} (ID: {profile.id}) is not a manager, skipping...')
                    )
                    