from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ...models import (
    ActionItem, Project, Course, CourseCategory, EmployeeProfile, ProjectAllocation,
    Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
)
from datetime import datetime, date, timedelta
import random


class Command(BaseCommand):
    help = 'Create dummy data for all models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=15,
            help='Number of users to create (default: 15)',
        )
        parser.add_argument(
            '--projects',
            type=int,
            default=8,
            help='Number of projects to create (default: 8)',
        )
        parser.add_argument(
            '--courses',
            type=int,
            default=12,
            help='Number of courses to create (default: 12)',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing data before creating new data',
        )

    def handle(self, *args, **options):
        if options['clear']:
            self.stdout.write(self.style.WARNING('Clearing existing data...'))
            self.clear_data()

        num_users = options['users']
        num_projects = options['projects']
        num_courses = options['courses']

        self.stdout.write(self.style.SUCCESS('Creating dummy data...'))

        # Create users and employee profiles
        users = self.create_users(num_users)
        self.stdout.write(self.style.SUCCESS(f'Created {len(users)} users with profiles'))

        # Create course categories and courses
        categories = self.create_course_categories()
        courses = self.create_courses(categories, num_courses)
        self.stdout.write(self.style.SUCCESS(f'Created {len(courses)} courses'))

        # Create projects
        projects = self.create_projects(num_projects)
        self.stdout.write(self.style.SUCCESS(f'Created {len(projects)} projects'))

        # Create project allocations
        allocations = self.create_project_allocations(users, projects)
        self.stdout.write(self.style.SUCCESS(f'Created {len(allocations)} project allocations'))

        # Create action items
        action_items = self.create_action_items(users)
        self.stdout.write(self.style.SUCCESS(f'Created {len(action_items)} action items'))

        # Create surveys with manager-associate assignments
        managers = [user for user in users if hasattr(user, 'employee_profile') and user.employee_profile.is_manager]
        associates = [user for user in users if hasattr(user, 'employee_profile') and not user.employee_profile.is_manager]
        surveys = self.create_surveys(managers, associates)
        self.stdout.write(self.style.SUCCESS(f'Created {len(surveys)} surveys with questions and responses'))

        self.stdout.write(self.style.SUCCESS('Dummy data creation completed successfully!'))

    def clear_data(self):
        """Clear existing data"""
        self.stdout.write('Deleting existing data...')
        # Delete survey-related data first (due to foreign key constraints)
        SurveyAnswer.objects.all().delete()
        SurveyResponse.objects.all().delete()
        SurveyQuestion.objects.all().delete()
        Survey.objects.all().delete()
        # Delete other data
        ProjectAllocation.objects.all().delete()
        EmployeeProfile.objects.all().delete()
        ActionItem.objects.all().delete()
        Project.objects.all().delete()
        Course.objects.all().delete()
        CourseCategory.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        self.stdout.write('✅ Existing data cleared')

    def create_users(self, count):
        """Create users with employee profiles and manager-associate relationships"""
        users = []
        managers = []
        
        # Sample names and data
        first_names = [
            'John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Lisa',
            'James', 'Maria', 'William', 'Jennifer', 'Richard', 'Patricia', 'Charles',
            'Linda', 'Joseph', 'Elizabeth', 'Thomas', 'Barbara', 'Mark', 'Susan',
            'Kevin', 'Nancy', 'Brian', 'Betty', 'Edward', 'Helen', 'Ronald', 'Sandra'
        ]
        
        last_names = [
            'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
            'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez',
            'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
            'Lee', 'Perez', 'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker'
        ]
        
        risk_levels = ['High', 'Medium', 'Low']
        trigger_options = ['MH', 'MT', 'CO', 'PR']
        
        # Create specific manager and associate users for testing
        test_users = [
            {'username': 'manager_user', 'first_name': 'Manager', 'last_name': 'User', 'is_manager': True},
            {'username': 'associate_user', 'first_name': 'Associate', 'last_name': 'User', 'is_manager': False},
            {'username': 'john_manager', 'first_name': 'John', 'last_name': 'Manager', 'is_manager': True},
            {'username': 'jane_associate', 'first_name': 'Jane', 'last_name': 'Associate', 'is_manager': False},
        ]
        
        # Create test users first
        for test_user in test_users:
            user = User.objects.create_user(
                username=test_user['username'],
                email=f"{test_user['username']}@company.com",
                first_name=test_user['first_name'],
                last_name=test_user['last_name'],
                password='password123'
            )
            users.append(user)
            if test_user['is_manager']:
                managers.append(user)
        
        # Create remaining users
        remaining_count = count - len(test_users)
        manager_ratio = 0.25  # 25% of remaining users will be managers
        num_managers = max(1, int(remaining_count * manager_ratio))
        
        for i in range(remaining_count):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            username = f"{first_name.lower()}.{last_name.lower()}{i+len(test_users)+1}"
            email = f"{username}@company.com"
            
            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password='password123'
            )
            users.append(user)
            
            # Designate some users as managers
            if i < num_managers:
                managers.append(user)
        
        # Create employee profiles with manager-associate relationships
        profile_pic_urls = [
            'https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=150',
            'https://images.unsplash.com/photo-1494790108755-2616b612b786?w=150',
            'https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150',
            'https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=150',
            'https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150',
        ]
        
        # Create profiles for all users with manager relationships
        for user in users:
            # Assign manager (associates get random managers, managers have no manager or senior manager)
            manager = None
            if user not in managers:  # This is an associate
                manager = random.choice(managers) if managers else None
            elif len(managers) > 1:  # This is a manager, might have a senior manager
                # 30% chance a manager reports to another manager (senior manager structure)
                if random.random() < 0.3:
                    potential_managers = [m for m in managers if m != user]
                    if potential_managers:
                        manager = random.choice(potential_managers)
            
            # Generate random triggers
            all_triggers = random.sample(trigger_options, random.randint(1, 3))
            primary_trigger = random.choice(trigger_options)
            
            EmployeeProfile.objects.create(
                user=user,
                manager=manager,
                profile_pic=random.choice(profile_pic_urls),
                age=random.randint(22, 55),
                mental_health=random.choice(risk_levels),
                motivation_factor=random.choice(risk_levels),
                career_opportunities=random.choice(risk_levels),
                personal_reason=random.choice(risk_levels),
                manager_assessment_risk=random.choice(risk_levels),
                all_triggers=','.join(all_triggers),
                primary_trigger=primary_trigger
            )
        
        # Print manager-associate relationships for debugging
        self.stdout.write(self.style.SUCCESS(f'\nCreated {len(managers)} managers and {len(users) - len(managers)} associates'))
        for manager in managers:
            team_size = EmployeeProfile.objects.filter(manager=manager).count()
            self.stdout.write(f'  Manager: {manager.username} ({manager.first_name} {manager.last_name}) - Team size: {team_size}')
        
        return users

    def create_course_categories(self):
        """Create course categories"""
        categories_data = [
            {'name': 'Technical Skills', 'description': 'Programming, software development, and technical competencies'},
            {'name': 'Leadership', 'description': 'Management and leadership development courses'},
            {'name': 'Communication', 'description': 'Soft skills and communication training'},
            {'name': 'Project Management', 'description': 'Project planning, execution, and management methodologies'},
            {'name': 'Data Science', 'description': 'Analytics, machine learning, and data visualization'},
            {'name': 'Design', 'description': 'UI/UX design and creative skills development'},
        ]
        
        categories = []
        for cat_data in categories_data:
            category, created = CourseCategory.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )
            categories.append(category)
        
        return categories

    def create_courses(self, categories, count):
        """Create courses"""
        course_titles = [
            'Advanced Python Programming',
            'React.js Fundamentals',
            'Leadership in Tech',
            'Agile Project Management',
            'Data Visualization with D3.js',
            'UX Design Principles',
            'Machine Learning Basics',
            'Effective Communication',
            'DevOps Essentials',
            'Product Management 101',
            'Cloud Architecture',
            'Team Building Strategies',
            'API Design Best Practices',
            'Digital Marketing',
            'Cybersecurity Fundamentals',
        ]
        
        courses = []
        for i in range(min(count, len(course_titles))):
            title = course_titles[i]
            description = f"Comprehensive course covering {title.lower()} with practical examples and hands-on exercises."
            
            course = Course.objects.create(
                title=title,
                description=description,
                source=f"https://learning.company.com/courses/{title.lower().replace(' ', '-')}"
            )
            
            # Assign random categories (1-2 per course)
            selected_categories = random.sample(categories, random.randint(1, 2))
            course.category.set(selected_categories)
            
            courses.append(course)
        
        return courses

    def create_projects(self, count):
        """Create projects"""
        project_data = [
            {
                'title': 'Customer Portal Redesign',
                'description': 'Complete overhaul of the customer-facing portal with modern UI/UX',
                'criticality': 'High'
            },
            {
                'title': 'Mobile App Development',
                'description': 'Native mobile application for iOS and Android platforms',
                'criticality': 'High'
            },
            {
                'title': 'Data Analytics Dashboard',
                'description': 'Real-time analytics dashboard for business intelligence',
                'criticality': 'Medium'
            },
            {
                'title': 'API Modernization',
                'description': 'Upgrade legacy APIs to REST and GraphQL standards',
                'criticality': 'Medium'
            },
            {
                'title': 'Security Audit Implementation',
                'description': 'Implementation of security recommendations from recent audit',
                'criticality': 'High'
            },
            {
                'title': 'Internal Tools Enhancement',
                'description': 'Improvements to internal productivity tools',
                'criticality': 'Low'
            },
            {
                'title': 'Cloud Migration Phase 2',
                'description': 'Migration of remaining services to cloud infrastructure',
                'criticality': 'Medium'
            },
            {
                'title': 'Performance Optimization',
                'description': 'System-wide performance improvements and optimization',
                'criticality': 'Medium'
            },
        ]
        
        projects = []
        for i in range(min(count, len(project_data))):
            data = project_data[i]
            start_date = date.today() - timedelta(days=random.randint(30, 180))
            go_live_date = start_date + timedelta(days=random.randint(90, 365))
            
            project = Project.objects.create(
                title=data['title'],
                description=data['description'],
                start_date=start_date,
                go_live_date=go_live_date,
                status=random.choice(['Active', 'Inactive']),
                criticality=data['criticality'],
                source=f"https://project-management.company.com/projects/{data['title'].lower().replace(' ', '-')}"
            )
            
            projects.append(project)
        
        return projects

    def create_project_allocations(self, users, projects):
        """Create project allocations"""
        allocations = []
        
        for user in users:
            # Each user gets 1-3 project allocations
            num_allocations = random.randint(1, 3)
            selected_projects = random.sample(projects, min(num_allocations, len(projects)))
            
            total_allocation = 0
            for i, project in enumerate(selected_projects):
                # Ensure total allocation doesn't exceed 100%
                remaining_capacity = 100 - total_allocation
                if remaining_capacity <= 0:
                    break
                
                if i == len(selected_projects) - 1:  # Last allocation
                    allocation_percentage = remaining_capacity
                else:
                    max_allocation = min(remaining_capacity, 60)  # Max 60% per project
                    allocation_percentage = random.randint(20, max_allocation)
                
                start_date = date.today() - timedelta(days=random.randint(0, 90))
                end_date = None
                if random.choice([True, False]):  # 50% chance of having end date
                    end_date = start_date + timedelta(days=random.randint(90, 365))
                
                allocation = ProjectAllocation.objects.create(
                    employee=user,
                    project=project,
                    allocation_percentage=allocation_percentage,
                    start_date=start_date,
                    end_date=end_date,
                    is_active=random.choice([True, True, True, False])  # 75% active
                )
                
                # Also assign user to project's assigned_to ManyToMany field
                project.assigned_to.add(user)
                
                allocations.append(allocation)
                total_allocation += allocation_percentage
        
        return allocations

    def create_action_items(self, users):
        """Create action items"""
        action_titles = [
            'Complete security training',
            'Update project documentation',
            'Review code changes',
            'Attend team meeting',
            'Submit timesheet',
            'Complete performance review',
            'Update skills assessment',
            'Finish course assignment',
            'Prepare presentation',
            'Conduct user interview',
            'Fix critical bug',
            'Deploy to staging',
            'Write unit tests',
            'Update API documentation',
            'Review pull request',
        ]
        
        action_items = []
        for user in users:
            # Each user gets 2-5 action items
            num_items = random.randint(2, 5)
            
            for i in range(num_items):
                title = random.choice(action_titles)
                status = random.choice(['Pending', 'Completed'])
                
                # Make title unique by adding user ID and counter
                unique_title = f"{title} - {user.username} #{i+1}"
                
                # Check if this combination already exists
                if not ActionItem.objects.filter(assigned_to=user, title=unique_title).exists():
                    action_item = ActionItem.objects.create(
                        assigned_to=user,
                        title=unique_title,
                        status=status,
                        action=f"https://tasks.company.com/items/{random.randint(1000, 9999)}"
                    )
                    action_items.append(action_item)
        
        return action_items

    def create_surveys(self, managers, associates):
        """Create surveys with questions and assign to team members"""
        from datetime import timedelta
        from django.utils import timezone
        
        surveys = []
        
        # Survey templates with questions
        survey_templates = [
            {
                'title': 'Q4 Employee Wellness Check',
                'description': 'Quarterly wellness assessment to understand team mental health and work-life balance.',
                'survey_type': 'wellness',
                'target_audience': 'team',
                'questions': [
                    {'text': 'How would you rate your current stress level at work?', 'type': 'rating'},
                    {'text': 'Do you feel supported by your manager?', 'type': 'boolean'},
                    {'text': 'What aspects of work are causing you the most stress?', 'type': 'text'},
                    {'text': 'How satisfied are you with your work-life balance?', 'type': 'rating'},
                    {'text': 'Any suggestions for improving team wellness?', 'type': 'text'}
                ]
            },
            {
                'title': 'Project Feedback Survey',
                'description': 'Gather feedback on current project processes and team collaboration.',
                'survey_type': 'feedback',
                'target_audience': 'team',
                'questions': [
                    {'text': 'How clear are the project requirements and goals?', 'type': 'rating'},
                    {'text': 'Rate the effectiveness of team communication', 'type': 'rating'},
                    {'text': 'What project management tools work best for you?', 'type': 'choice', 'choices': ['Jira', 'Trello', 'Asana', 'Monday.com', 'Other']},
                    {'text': 'Are you satisfied with the current project timeline?', 'type': 'boolean'},
                    {'text': 'What improvements would you suggest for our project workflow?', 'type': 'text'}
                ]
            },
            {
                'title': 'Skills Development Assessment',
                'description': 'Identify skill gaps and development opportunities for team members.',
                'survey_type': 'skills',
                'target_audience': 'team',
                'questions': [
                    {'text': 'Rate your confidence in your current technical skills', 'type': 'scale'},
                    {'text': 'Which skills would you like to develop further?', 'type': 'text'},
                    {'text': 'Do you feel you have adequate learning resources?', 'type': 'boolean'},
                    {'text': 'How interested are you in leadership training?', 'type': 'rating'},
                    {'text': 'What type of training format do you prefer?', 'type': 'choice', 'choices': ['Online courses', 'In-person workshops', 'Mentoring', 'Self-study', 'Team projects']}
                ]
            },
            {
                'title': 'Job Satisfaction Survey',
                'description': 'Annual job satisfaction and career development survey.',
                'survey_type': 'satisfaction',
                'target_audience': 'team',
                'questions': [
                    {'text': 'Overall, how satisfied are you with your job?', 'type': 'rating'},
                    {'text': 'Do you see a clear career path at this company?', 'type': 'boolean'},
                    {'text': 'Rate your satisfaction with compensation and benefits', 'type': 'rating'},
                    {'text': 'How likely are you to recommend this company as a place to work?', 'type': 'scale'},
                    {'text': 'What would make you more satisfied in your role?', 'type': 'text'}
                ]
            },
            {
                'title': 'Goal Setting Workshop Feedback',
                'description': 'Feedback on recent goal setting session and future planning.',
                'survey_type': 'goals',
                'target_audience': 'team',
                'questions': [
                    {'text': 'How helpful was the goal setting workshop?', 'type': 'rating'},
                    {'text': 'Do you have clear goals for the next quarter?', 'type': 'boolean'},
                    {'text': 'What support do you need to achieve your goals?', 'type': 'text'},
                    {'text': 'Rate your confidence in achieving your set goals', 'type': 'rating'},
                    {'text': 'Would you like more frequent goal review sessions?', 'type': 'boolean'}
                ]
            }
        ]
        
        # Create surveys for each manager
        for manager in managers:
            # Get manager's team members
            team_members = [user for user in associates if hasattr(user, 'employee_profile') and user.employee_profile.manager == manager]
            
            if not team_members:
                continue
                
            # Create 2-3 surveys per manager
            selected_templates = random.sample(survey_templates, min(3, len(survey_templates)))
            
            for template in selected_templates:
                # Create survey
                start_date = timezone.now() - timedelta(days=random.randint(1, 30))
                end_date = start_date + timedelta(days=random.randint(14, 60))
                
                survey = Survey.objects.create(
                    title=template['title'],
                    description=template['description'],
                    survey_type=template['survey_type'],
                    status=random.choice(['active', 'active', 'closed']),  # 66% active
                    created_by=manager,
                    target_audience=template['target_audience'],
                    start_date=start_date,
                    end_date=end_date,
                    is_anonymous=random.choice([True, False])
                )
                
                # Create questions for the survey
                for i, question_data in enumerate(template['questions']):
                    question = SurveyQuestion.objects.create(
                        survey=survey,
                        question_text=question_data['text'],
                        question_type=question_data['type'],
                        choices=question_data.get('choices'),
                        is_required=True,
                        order=i + 1
                    )
                
                # Create responses for some team members (simulate partial completion)
                responding_members = random.sample(team_members, random.randint(1, len(team_members)))
                
                for member in responding_members:
                    # Create survey response
                    response = SurveyResponse.objects.create(
                        survey=survey,
                        respondent=member,
                        is_completed=random.choice([True, True, False])  # 66% completed
                    )
                    
                    # Create answers for completed responses
                    if response.is_completed:
                        for question in survey.questions.all():
                            answer = SurveyAnswer.objects.create(
                                response=response,
                                question=question
                            )
                            
                            # Generate realistic answers based on question type
                            if question.question_type == 'rating':
                                answer.answer_rating = random.randint(1, 5)
                            elif question.question_type == 'scale':
                                answer.answer_rating = random.randint(1, 10)
                            elif question.question_type == 'boolean':
                                answer.answer_boolean = random.choice([True, False])
                            elif question.question_type == 'choice' and question.choices:
                                answer.answer_choice = random.choice(question.choices)
                            elif question.question_type == 'text':
                                sample_responses = [
                                    'Great communication and clear expectations.',
                                    'Could use more flexible working hours.',
                                    'Team collaboration is excellent.',
                                    'Would like more professional development opportunities.',
                                    'Overall satisfied with current role and responsibilities.',
                                    'Need better work-life balance.',
                                    'Appreciate the supportive team environment.'
                                ]
                                answer.answer_text = random.choice(sample_responses)
                            
                            answer.save()
                
                surveys.append(survey)
        
        return surveys
