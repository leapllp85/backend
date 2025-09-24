from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.core.cache import caches
from apis.models import EmployeeProfile, Project, ProjectAllocation
from apis.signals import invalidate_all_team_caches
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Test cache invalidation signals'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear-all',
            action='store_true',
            help='Clear all team caches',
        )
        parser.add_argument(
            '--test-employee',
            type=int,
            help='Test cache invalidation for specific employee ID',
        )
        parser.add_argument(
            '--show-stats',
            action='store_true',
            help='Show cache statistics',
        )

    def handle(self, *args, **options):
        if options['clear_all']:
            self.clear_all_caches()
        
        if options['test_employee']:
            self.test_employee_cache(options['test_employee'])
        
        if options['show_stats']:
            self.show_cache_stats()
        
        if not any([options['clear_all'], options['test_employee'], options['show_stats']]):
            self.run_full_test()

    def clear_all_caches(self):
        """Clear all team caches"""
        self.stdout.write("Clearing all team caches...")
        result = invalidate_all_team_caches()
        if result:
            self.stdout.write(self.style.SUCCESS("✓ All caches cleared successfully"))
        else:
            self.stdout.write(self.style.ERROR("✗ Error clearing caches"))

    def test_employee_cache(self, employee_id):
        """Test cache invalidation for specific employee"""
        try:
            user = User.objects.get(id=employee_id)
            employee_profile = user.employee_profile
            
            self.stdout.write(f"Testing cache invalidation for: {user.username}")
            
            # Trigger cache invalidation by updating employee profile
            employee_profile.mental_health = 'Medium' if employee_profile.mental_health != 'Medium' else 'High'
            employee_profile.save()
            
            self.stdout.write(self.style.SUCCESS("✓ Cache invalidation triggered successfully"))
            
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"✗ Employee with ID {employee_id} not found"))
        except EmployeeProfile.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"✗ Employee profile for user {employee_id} not found"))

    def show_cache_stats(self):
        """Show cache statistics"""
        self.stdout.write("Cache Statistics:")
        self.stdout.write("-" * 50)
        
        # Team cache stats
        try:
            team_cache = caches['team_cache']
            self.stdout.write(f"Team Cache: Available")
            
            # Try to get some stats (Redis specific)
            if hasattr(team_cache, '_cache'):
                cache_info = team_cache._cache.info()
                self.stdout.write(f"  - Used Memory: {cache_info.get('used_memory_human', 'N/A')}")
                self.stdout.write(f"  - Connected Clients: {cache_info.get('connected_clients', 'N/A')}")
                self.stdout.write(f"  - Keyspace Hits: {cache_info.get('keyspace_hits', 'N/A')}")
                self.stdout.write(f"  - Keyspace Misses: {cache_info.get('keyspace_misses', 'N/A')}")
        except Exception as e:
            self.stdout.write(f"Team Cache: Error - {e}")
        
        # Default cache stats
        try:
            default_cache = caches['default']
            self.stdout.write(f"Default Cache: Available")
        except Exception as e:
            self.stdout.write(f"Default Cache: Error - {e}")

    def run_full_test(self):
        """Run comprehensive cache invalidation tests"""
        self.stdout.write("Running comprehensive cache invalidation tests...")
        self.stdout.write("=" * 60)
        
        # Test 1: Employee profile update
        self.stdout.write("\n1. Testing Employee Profile Update Cache Invalidation")
        try:
            employee = EmployeeProfile.objects.filter(is_manager=False).first()
            if employee:
                old_value = employee.mental_health
                new_value = 'High' if old_value != 'High' else 'Medium'
                
                self.stdout.write(f"   Updating {employee.user.username}: {old_value} -> {new_value}")
                employee.mental_health = new_value
                employee.save()
                
                self.stdout.write(self.style.SUCCESS("   ✓ Employee profile cache invalidation triggered"))
            else:
                self.stdout.write(self.style.WARNING("   ⚠ No non-manager employees found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error: {e}"))
        
        # Test 2: Project allocation update
        self.stdout.write("\n2. Testing Project Allocation Cache Invalidation")
        try:
            allocation = ProjectAllocation.objects.first()
            if allocation:
                old_criticality = allocation.criticality
                new_criticality = 'High' if old_criticality != 'High' else 'Medium'
                
                self.stdout.write(f"   Updating allocation for {allocation.employee.username}: {old_criticality} -> {new_criticality}")
                allocation.criticality = new_criticality
                allocation.save()
                
                self.stdout.write(self.style.SUCCESS("   ✓ Project allocation cache invalidation triggered"))
            else:
                self.stdout.write(self.style.WARNING("   ⚠ No project allocations found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error: {e}"))
        
        # Test 3: Project update
        self.stdout.write("\n3. Testing Project Update Cache Invalidation")
        try:
            project = Project.objects.first()
            if project:
                old_status = project.status
                new_status = 'ACTIVE' if old_status != 'ACTIVE' else 'COMPLETED'
                
                self.stdout.write(f"   Updating project {project.title}: {old_status} -> {new_status}")
                project.status = new_status
                project.save()
                
                self.stdout.write(self.style.SUCCESS("   ✓ Project cache invalidation triggered"))
            else:
                self.stdout.write(self.style.WARNING("   ⚠ No projects found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error: {e}"))
        
        # Test 4: User profile update
        self.stdout.write("\n4. Testing User Profile Update Cache Invalidation")
        try:
            user = User.objects.filter(employee_profile__isnull=False).first()
            if user:
                old_name = user.first_name
                new_name = f"{old_name}_test" if not old_name.endswith('_test') else old_name.replace('_test', '')
                
                self.stdout.write(f"   Updating user {user.username}: {old_name} -> {new_name}")
                user.first_name = new_name
                user.save()
                
                self.stdout.write(self.style.SUCCESS("   ✓ User profile cache invalidation triggered"))
            else:
                self.stdout.write(self.style.WARNING("   ⚠ No users with employee profiles found"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"   ✗ Error: {e}"))
        
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("Cache invalidation tests completed!"))
        self.stdout.write("\nCheck the logs for detailed cache invalidation messages.")
