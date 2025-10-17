from django.core.management.base import BaseCommand
from django.db import transaction
from apis.models.employees import Trigger
from django.db.utils import IntegrityError


class Command(BaseCommand):
    help = 'Populate Trigger model with predefined trigger data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing triggers before adding new ones',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be added without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        clear_existing = options['clear']
        
        # Trigger data with format: (primary_trigger_code, trigger_name)
        trigger_data = [
            ('CO', 'No growth'),
            ('CO', 'Onsite Opputunity'),
            ('CO', 'Lack Of role clarity'),
            ('PR', 'Health Issues'),
            ('PR', 'Higher Education'),
            ('MH', 'Unrealistic Expectations'),
            ('MH', 'Concerns with peers'),
            ('MH', 'Concerns with Manager'),
            ('MT', 'Return to Office'),
            ('MT', 'Rewards and Recognition'),
        ]
        
        self.stdout.write(
            self.style.SUCCESS('Starting trigger data population process...')
        )
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )
        
        # Clear existing triggers if requested
        if clear_existing and not dry_run:
            existing_count = Trigger.objects.count()
            Trigger.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f'Cleared {existing_count} existing triggers')
            )
        
        created_count = 0
        updated_count = 0
        skipped_count = 0
        
        with transaction.atomic():
            for primary_trigger_code, trigger_name in trigger_data:
                try:
                    if not dry_run:
                        trigger, created = Trigger.objects.get_or_create(
                            name=trigger_name,
                            defaults={'primary_trigger': primary_trigger_code}
                        )
                        
                        if created:
                            created_count += 1
                            self.stdout.write(
                                f'  ✓ Created: {trigger_name} ({primary_trigger_code})'
                            )
                        else:
                            # Update primary_trigger if it's different
                            if trigger.primary_trigger != primary_trigger_code:
                                trigger.primary_trigger = primary_trigger_code
                                trigger.save()
                                updated_count += 1
                                self.stdout.write(
                                    f'  ↻ Updated: {trigger_name} ({primary_trigger_code})'
                                )
                            else:
                                skipped_count += 1
                                self.stdout.write(
                                    f'  - Skipped: {trigger_name} (already exists with same data)'
                                )
                    else:
                        # Dry run - just show what would be done
                        existing = Trigger.objects.filter(name=trigger_name).first()
                        if existing:
                            if existing.primary_trigger != primary_trigger_code:
                                self.stdout.write(
                                    f'  ↻ Would update: {trigger_name} ({existing.primary_trigger} → {primary_trigger_code})'
                                )
                            else:
                                self.stdout.write(
                                    f'  - Would skip: {trigger_name} (already exists with same data)'
                                )
                        else:
                            self.stdout.write(
                                f'  ✓ Would create: {trigger_name} ({primary_trigger_code})'
                            )
                
                except IntegrityError as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Error with {trigger_name}: {str(e)}')
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f'  ✗ Unexpected error with {trigger_name}: {str(e)}')
                    )
        
        # Summary
        self.stdout.write('\n' + '='*50)
        self.stdout.write('Trigger population completed!')
        
        if not dry_run:
            self.stdout.write(f'Triggers created: {created_count}')
            self.stdout.write(f'Triggers updated: {updated_count}')
            self.stdout.write(f'Triggers skipped: {skipped_count}')
            self.stdout.write(f'Total triggers in database: {Trigger.objects.count()}')
        else:
            self.stdout.write(
                self.style.WARNING('DRY RUN COMPLETED - No actual changes were made')
            )
        
        # Display all triggers
        self.stdout.write('\n' + 'Current triggers in database:')
        for trigger in Trigger.objects.all().order_by('primary_trigger', 'name'):
            primary_trigger_display = dict(Trigger._meta.get_field('primary_trigger').choices).get(
                trigger.primary_trigger, trigger.primary_trigger
            ) if trigger.primary_trigger else 'No Category'
            self.stdout.write(f'  • {trigger.name} ({trigger.primary_trigger} - {primary_trigger_display})')
