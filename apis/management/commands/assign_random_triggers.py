from django.core.management.base import BaseCommand
from django.db import transaction
from apis.models.employees import EmployeeProfile, Trigger
import random


class Command(BaseCommand):
    help = 'Randomly assign multiple triggers to all EmployeeProfile records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--min-triggers',
            type=int,
            default=1,
            help='Minimum number of triggers to assign per employee (default: 1)',
        )
        parser.add_argument(
            '--max-triggers',
            type=int,
            default=4,
            help='Maximum number of triggers to assign per employee (default: 4)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be assigned without making changes',
        )
        parser.add_argument(
            '--clear-existing',
            action='store_true',
            help='Clear existing trigger assignments before adding new ones',
        )
        parser.add_argument(
            '--seed',
            type=int,
            help='Random seed for reproducible results',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        min_triggers = options['min_triggers']
        max_triggers = options['max_triggers']
        clear_existing = options['clear_existing']
        seed = options['seed']
        
        # Set random seed if provided
        if seed:
            random.seed(seed)
            self.stdout.write(f'Using random seed: {seed}')
        
        self.stdout.write(
            self.style.SUCCESS('Starting random trigger assignment process...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Validate arguments
        if min_triggers < 1:
            self.stdout.write(
                self.style.ERROR('min-triggers must be at least 1')
            )
            return
        
        if max_triggers < min_triggers:
            self.stdout.write(
                self.style.ERROR('max-triggers must be greater than or equal to min-triggers')
            )
            return
        
        # Get all triggers and employees
        all_triggers = list(Trigger.objects.all())
        all_employees = EmployeeProfile.objects.all()
        
        if not all_triggers:
            self.stdout.write(
                self.style.ERROR('No triggers found in database. Please run populate_triggers command first.')
            )
            return
        
        if not all_employees:
            self.stdout.write(
                self.style.WARNING('No employee profiles found to assign triggers to.')
            )
            return
        
        self.stdout.write(f'Found {len(all_triggers)} triggers and {all_employees.count()} employees')
        self.stdout.write(f'Will assign {min_triggers}-{max_triggers} triggers per employee')
        
        # Display available triggers
        self.stdout.write('\nAvailable triggers:')
        for trigger in all_triggers:
            primary_display = dict(Trigger._meta.get_field('primary_trigger').choices).get(
                trigger.primary_trigger, trigger.primary_trigger
            ) if trigger.primary_trigger else 'No Category'
            self.stdout.write(f'  • {trigger.name} ({trigger.primary_trigger} - {primary_display})')
        
        assigned_count = 0
        total_assignments = 0
        
        with transaction.atomic():
            for employee in all_employees:
                try:
                    # Clear existing assignments if requested
                    if clear_existing and not dry_run:
                        employee.all_triggers.clear()
                    
                    # Determine number of triggers to assign
                    num_triggers = random.randint(min_triggers, max_triggers)
                    
                    # Randomly select triggers (without replacement)
                    selected_triggers = random.sample(all_triggers, min(num_triggers, len(all_triggers)))
                    
                    if not dry_run:
                        # Add selected triggers to employee
                        for trigger in selected_triggers:
                            employee.all_triggers.add(trigger)
                    
                    assigned_count += 1
                    total_assignments += len(selected_triggers)
                    
                    # Display assignment
                    trigger_names = [t.name for t in selected_triggers]
                    action = "Would assign" if dry_run else "Assigned"
                    self.stdout.write(
                        f'  {action} {len(selected_triggers)} triggers to {employee.user.username}: {", ".join(trigger_names)}'
                    )
                
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  Error processing employee {employee.user.username}: {str(e)}')
                    )
        
        # Summary
        self.stdout.write('\n' + '='*60)
        self.stdout.write('Random trigger assignment completed!')
        self.stdout.write(f'Employees processed: {assigned_count}')
        self.stdout.write(f'Total trigger assignments: {total_assignments}')
        self.stdout.write(f'Average triggers per employee: {total_assignments/assigned_count:.1f}' if assigned_count > 0 else 'N/A')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETED - No actual changes were made')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS('All assignments completed successfully!')
            )
        
        # Display statistics by trigger category
        if not dry_run:
            self.stdout.write('\n' + 'Assignment statistics by trigger category:')
            for category_code, category_name in Trigger._meta.get_field('primary_trigger').choices:
                category_triggers = Trigger.objects.filter(primary_trigger=category_code)
                total_assignments_for_category = sum(
                    employee.all_triggers.filter(primary_trigger=category_code).count() 
                    for employee in all_employees
                )
                self.stdout.write(
                    f'  {category_name} ({category_code}): {total_assignments_for_category} assignments across {category_triggers.count()} triggers'
                )
