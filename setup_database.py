#!/usr/bin/env python
"""
Database setup script for Corporate MVP
This script will create migrations, apply them, and optionally create dummy data
"""

import os
import sys
import subprocess

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"\n🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed:")
        print(f"Error: {e.stderr}")
        return False

def main():
    print("🚀 Corporate MVP Database Setup")
    print("=" * 50)
    
    # Check if we're in the right directory
    if not os.path.exists('manage.py'):
        print("❌ Error: manage.py not found. Please run this script from the Django project root.")
        sys.exit(1)
    
    # Step 1: Create migrations
    if not run_command("python manage.py makemigrations", "Creating migrations"):
        print("⚠️  Migration creation failed. Continuing anyway...")
    
    # Step 2: Apply migrations
    if not run_command("python manage.py migrate", "Applying migrations"):
        print("❌ Migration failed. Cannot continue.")
        sys.exit(1)
    
    # Step 3: Ask about creating dummy data
    create_dummy = input("\n Would you like to create dummy data? (y/n): ").lower().strip()
    
    if create_dummy in ['y', 'yes']:
        # Step 4: Create dummy data
        print("\n Creating dummy data...")
        print("This will create a complete role-based system with:")
        print("\n Users & Roles:")
        print("- 15 total users with employee profiles")
        print("- ~4 managers (25% ratio) with team management capabilities")
        print("- ~11 associates reporting to managers")
        print("- Realistic manager-associate relationships")
        print("\n Test Users for API Testing:")
        print("- manager_user (password: password123) - Manager role")
        print("- associate_user (password: password123) - Associate role")
        print("- john_manager & jane_associate - Additional test users")
        print("\n Business Data:")
        print("- 8 projects with different criticality levels")
        print("- 12 courses across 6 categories")
        print("- Project allocations for all users")
        print("- Action items with role-based assignments")
        print("- Survey data for manager-published surveys")
        print("\n Role-Based Features:")
        print("- Managers can create/assign action items and courses")
        print("- Associates can view all but only update their own items")
        print("- Team-based data access and permissions")
        print("")
        proceed = input("Proceed? (y/n): ").lower().strip()
        
        if proceed in ['y', 'yes']:
            if not run_command("python manage.py create_dummy_data --clear", "Creating dummy data (clearing existing data first)"):
                print(" Dummy data creation failed.")
                sys.exit(1)
            else:
                print("\n Database setup completed successfully!")
                print("\nYou can now:")
                print("1. Start the development server: python manage.py runserver")
                print("2. Access the admin panel: http://127.0.0.1:8000/admin/")
                print("3. Test the APIs using the endpoints in urls.py")
        else:
            print("  Skipping dummy data creation.")
            print("⏭️  Skipping dummy data creation.")
    else:
        print("⏭️  Skipping dummy data creation.")
    
    print("\n✨ Setup complete! Your database is ready to use.")

if __name__ == "__main__":
    main()
