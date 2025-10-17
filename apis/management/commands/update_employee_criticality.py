from django.core.management.base import BaseCommand
from django.db import transaction
from apis.models.employees import EmployeeProfile
from django.utils import timezone


class Command(BaseCommand):
    help = 'Update employee_project_criticality and suggested_risk for all EmployeeProfile records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Number of records to process in each batch (default: 100)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        batch_size = options['batch_size']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting employee criticality update process...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Get all EmployeeProfile records
        total_profiles = EmployeeProfile.objects.count()
        self.stdout.write(f'Found {total_profiles} employee profiles to process')
        
        if total_profiles == 0:
            self.stdout.write(
                self.style.WARNING('No employee profiles found to update')
            )
            return
        
        updated_count = 0
        error_count = 0
        
        # Process in batches to avoid memory issues
        for offset in range(0, total_profiles, batch_size):
            batch_profiles = EmployeeProfile.objects.all()[offset:offset + batch_size]
            
            self.stdout.write(f'Processing batch {offset//batch_size + 1}: records {offset + 1} to {min(offset + batch_size, total_profiles)}')
            
            with transaction.atomic():
                for profile in batch_profiles:
                    try:
                        # Store old values for comparison
                        old_project_criticality = profile.employee_project_criticality
                        old_suggested_risk = profile.suggested_risk
                        
                        # Calculate new values
                        new_project_criticality = profile.calculate_employee_project_criticality()
                        new_suggested_risk = profile.calculate_suggested_risk()
                        
                        # Check if values changed
                        project_criticality_changed = old_project_criticality != new_project_criticality
                        suggested_risk_changed = old_suggested_risk != new_suggested_risk
                        
                        if project_criticality_changed or suggested_risk_changed:
                            if not dry_run:
                                # Update the fields directly without triggering save() method
                                # to avoid any potential side effects
                                EmployeeProfile.objects.filter(id=profile.id).update(
                                    employee_project_criticality=new_project_criticality,
                                    suggested_risk=new_suggested_risk,
                                    updated_at=timezone.now()
                                )
                            
                            updated_count += 1
                            
                            # Log the changes
                            changes = []
                            if project_criticality_changed:
                                changes.append(f'project_criticality: {old_project_criticality} → {new_project_criticality}')
                            if suggested_risk_changed:
                                changes.append(f'suggested_risk: {old_suggested_risk} → {new_suggested_risk}')
                            
                            self.stdout.write(
                                f'  Employee {profile.user.username} (ID: {profile.id}): {", ".join(changes)}'
                            )
                        else:
                            self.stdout.write(
                                f'  Employee {profile.user.username} (ID: {profile.id}): No changes needed'
                            )
                    
                    except Exception as e:
                        error_count += 1
                        self.stdout.write(
                            self.style.ERROR(
                                f'  Error processing employee {profile.user.username} (ID: {profile.id}): {str(e)}'
                            )
                        )
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write(f'Update process completed!')
        self.stdout.write(f'Total profiles processed: {total_profiles}')
        self.stdout.write(f'Profiles updated: {updated_count}')
        self.stdout.write(f'Profiles with no changes: {total_profiles - updated_count - error_count}')
        
        if error_count > 0:
            self.stdout.write(
                self.style.ERROR(f'Profiles with errors: {error_count}')
            )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETED - No actual changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('All updates completed successfully!')
            )
