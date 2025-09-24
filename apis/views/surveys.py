from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from django.contrib.auth.models import User
from django.db.models import Count, Avg, Q
from django.utils import timezone
from ..models import Survey, SurveyQuestion, SurveyResponse, SurveyAnswer, EmployeeProfile, ActionItem
from ..serializers import SurveySerializer, SurveyQuestionSerializer, SurveyResponseSerializer
from ..permissions import IsManager, IsManagerOrAssociate, CanAccessTeamData

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class SurveyListAPIView(APIView):
    """API for listing available surveys with enhanced team visibility"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    
    def get(self, request):
        """Get available surveys for the current user"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get search query parameter
        search_query = request.query_params.get('search', '').strip()
        
        # Get active surveys
        now = timezone.now()
        surveys = Survey.objects.filter(
            status__in=['active', 'closed']
        ).prefetch_related('questions').select_related('created_by')
        
        # Apply search filter if provided
        if search_query:
            surveys = surveys.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(survey_type__icontains=search_query) |
                Q(target_audience__icontains=search_query)
            )
        
        # Filter based on target audience and user role
        available_surveys = []
        team_surveys = []
        all_surveys = []
        
        for survey in surveys:
            if survey.target_audience == 'all':
                available_surveys.append(survey)
                all_surveys.append(survey)
            elif survey.target_audience == 'team' and user_profile.manager:
                # Check if survey was created by user's manager
                if survey.created_by == user_profile.manager:
                    available_surveys.append(survey)
                    team_surveys.append(survey)
        
        # Check which surveys user has already completed
        completed_survey_ids = SurveyResponse.objects.filter(
            respondent=user,
            is_completed=True
        ).values_list('survey_id', flat=True)
        
        # Prepare response data with enhanced information
        survey_data = []
        for survey in available_surveys:
            is_completed = survey.id in completed_survey_ids
            is_team_survey = survey in team_surveys
            
            survey_info = {
                'id': survey.id,
                'title': survey.title,
                'description': survey.description,
                'survey_type': survey.survey_type,
                'target_audience': survey.target_audience,
                'start_date': survey.start_date,
                'end_date': survey.end_date,
                'is_anonymous': survey.is_anonymous,
                'question_count': survey.questions.count(),
                'is_completed': is_completed,
                'status': 'completed' if is_completed else ('expired' if not survey.is_active else 'pending'),
                'can_respond': survey.can_accept_responses and not is_completed,
                'created_by': {
                    'id': survey.created_by.id,
                    'name': f"{survey.created_by.first_name} {survey.created_by.last_name}",
                    'username': survey.created_by.username
                },
                'is_team_survey': is_team_survey,
                'source': 'manager' if is_team_survey else 'organization',
                'priority': 'high' if is_team_survey else 'medium',
                'days_remaining': (survey.end_date.date() - now.date()).days if survey.end_date else None
            }
            survey_data.append(survey_info)
        
        # Sort surveys: team surveys first, then by priority and due date
        survey_data.sort(key=lambda x: (
            not x['is_team_survey'],  # Team surveys first
            x['is_completed'],        # Pending surveys first
            x['days_remaining'] if x['days_remaining'] is not None else 999  # Soonest deadline first
        ))
        
        # Apply pagination
        paginator = StandardResultsSetPagination()
        paginated_surveys = paginator.paginate_queryset(survey_data, request)
        
        return paginator.get_paginated_response({
            'surveys': paginated_surveys,
            'summary': {
                'total_available': len(available_surveys),
                'team_surveys': len(team_surveys),
                'organization_surveys': len(all_surveys),
                'completed': len(completed_survey_ids),
                'pending': len([s for s in survey_data if not s['is_completed']]),
                'high_priority': len([s for s in survey_data if s['priority'] == 'high' and not s['is_completed']])
            },
            'user_info': {
                'username': user.username,
                'role': user_profile.role,
                'manager': f"{user_profile.manager.first_name} {user_profile.manager.last_name}" if user_profile.manager else None
            },
            'search_query': search_query if search_query else None,
            'total_results': len(survey_data)
        })


class SurveyDetailAPIView(APIView):
    """API for getting survey details and questions"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, survey_id):
        """Get survey details with questions"""
        user = request.user
        
        try:
            survey = Survey.objects.get(id=survey_id)
        except Survey.DoesNotExist:
            return Response({
                'error': 'Survey not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if survey is viewable (allow expired surveys for viewing)
        if not survey.is_viewable:
            return Response({
                'error': 'Survey is not available'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user has already completed this survey
        existing_response = SurveyResponse.objects.filter(
            survey=survey,
            respondent=user,
            is_completed=True
        ).first()
        
        # Add survey status information to response
        survey_status = {
            'is_active': survey.is_active,
            'can_accept_responses': survey.can_accept_responses,
            'is_expired': not survey.is_active and survey.status == 'active'
        }
        
        if existing_response:
            return Response({
                'error': 'You have already completed this survey'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create survey response for tracking
        survey_response, created = SurveyResponse.objects.get_or_create(
            survey=survey,
            respondent=user if not survey.is_anonymous else None,
            defaults={'is_completed': False}
        )
        
        # Get survey questions
        questions = survey.questions.all()
        questions_data = []
        
        for question in questions:
            question_data = {
                'id': question.id,
                'question_text': question.question_text,
                'question_type': question.question_type,
                'choices': question.choices,
                'is_required': question.is_required,
                'order': question.order
            }
            
            # Get existing answer if any
            existing_answer = SurveyAnswer.objects.filter(
                response=survey_response,
                question=question
            ).first()
            
            if existing_answer:
                question_data['current_answer'] = existing_answer.answer_value
            
            questions_data.append(question_data)
        
        return Response({
            'survey': {
                'id': survey.id,
                'title': survey.title,
                'description': survey.description,
                'survey_type': survey.survey_type,
                'is_anonymous': survey.is_anonymous,
                'start_date': survey.start_date,
                'end_date': survey.end_date,
                'status': survey.status,
                **survey_status
            },
            'questions': questions_data,
            'response_id': survey_response.id,
            'is_draft': not survey_response.is_completed
        })


class SurveyResponseAPIView(APIView):
    """API for submitting survey responses"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, survey_id):
        """Submit survey response"""
        user = request.user
        
        try:
            survey = Survey.objects.get(id=survey_id)
        except Survey.DoesNotExist:
            return Response({
                'error': 'Survey not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Only allow responses for active surveys
        if not survey.can_accept_responses:
            return Response({
                'error': 'Survey is no longer accepting responses'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get or create survey response
        survey_response, created = SurveyResponse.objects.get_or_create(
            survey=survey,
            respondent=user if not survey.is_anonymous else None,
            defaults={'is_completed': False}
        )
        
        if survey_response.is_completed:
            return Response({
                'error': 'Survey already completed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        answers_data = request.data.get('answers', [])
        
        # Validate and save answers
        for answer_data in answers_data:
            question_id = answer_data.get('question_id')
            
            try:
                question = SurveyQuestion.objects.get(id=question_id, survey=survey)
            except SurveyQuestion.DoesNotExist:
                continue
            
            # Get or create answer
            answer, created = SurveyAnswer.objects.get_or_create(
                response=survey_response,
                question=question
            )
            
            # Set answer based on question type
            if question.question_type == 'text':
                answer.answer_text = answer_data.get('answer')
            elif question.question_type in ['rating', 'scale']:
                answer.answer_rating = int(answer_data.get('answer', 0))
            elif question.question_type == 'choice':
                answer.answer_choice = answer_data.get('answer')
            elif question.question_type == 'boolean':
                answer.answer_boolean = bool(answer_data.get('answer'))
            
            answer.save()
        
        # Mark as completed if specified
        if request.data.get('is_completed', False):
            survey_response.is_completed = True
            survey_response.save()
        
        return Response({
            'message': 'Survey response saved successfully',
            'is_completed': survey_response.is_completed,
            'response_id': survey_response.id
        })


class MySurveyResponsesAPIView(APIView):
    """API for getting user's survey response history"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's survey response history"""
        user = request.user
        
        responses = SurveyResponse.objects.filter(
            respondent=user
        ).select_related('survey').order_by('-submitted_at')
        
        response_data = []
        for response in responses:
            response_info = {
                'id': response.id,
                'survey_title': response.survey.title,
                'survey_type': response.survey.survey_type,
                'is_completed': response.is_completed,
                'submitted_at': response.submitted_at,
                'is_anonymous': response.survey.is_anonymous
            }
            response_data.append(response_info)
        
        return Response({
            'responses': response_data,
            'total_responses': len(response_data),
            'completed_responses': len([r for r in response_data if r['is_completed']])
        })


class ManagerSurveyPublishAPIView(APIView):
    """API for managers to publish surveys specifically to their team"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def post(self, request):
        """Publish a new survey to the manager's team"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get team members count for validation
        team_members = User.objects.filter(employee_profile__manager=user)
        if not team_members.exists():
            return Response({
                'error': 'No team members found. Cannot publish team survey.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Create survey data with team targeting
        survey_data = request.data.copy()
        survey_data['created_by'] = user.id
        survey_data['target_audience'] = 'team'  # Force team targeting
        survey_data['status'] = 'active'  # Auto-activate team surveys
        
        # Validate required fields
        required_fields = ['title', 'description', 'survey_type', 'start_date', 'end_date']
        for field in required_fields:
            if field not in survey_data or not survey_data[field]:
                return Response({
                    'error': f'Field {field} is required'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = SurveySerializer(data=survey_data)
        if serializer.is_valid():
            survey = serializer.save()
            
            # Create questions if provided
            questions_data = request.data.get('questions', [])
            for i, question_data in enumerate(questions_data):
                question_data['survey'] = survey.id
                question_data['order'] = i + 1
                question_serializer = SurveyQuestionSerializer(data=question_data)
                if question_serializer.is_valid():
                    question_serializer.save()
            
            # Auto-create action items for team members
            self.create_survey_action_items(survey, team_members)
            
            return Response({
                'message': 'Survey published successfully to your team',
                'survey': serializer.data,
                'team_size': team_members.count(),
                'questions_added': len(questions_data),
                'action_items_created': team_members.count()
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def create_survey_action_items(self, survey, team_members):
        """Create action items for team members to complete the survey"""
        action_items = []
        for member in team_members:
            action_item = ActionItem(
                assigned_to=member,
                title=f"Complete Team Survey: {survey.title}",
                status='Pending',
                action=f"/surveys/{survey.id}"
            )
            action_items.append(action_item)
        
        # Bulk create action items
        ActionItem.objects.bulk_create(action_items)
    
    def get(self, request):
        """Get surveys published by this manager"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get surveys created by this manager
        surveys = Survey.objects.filter(
            created_by=user,
            target_audience='team'
        ).prefetch_related('questions', 'responses').order_by('-created_at')
        
        survey_data = []
        for survey in surveys:
            # Get response statistics
            total_responses = survey.responses.filter(is_completed=True).count()
            team_size = User.objects.filter(employee_profile__manager=user).count()
            
            survey_info = {
                'id': survey.id,
                'title': survey.title,
                'description': survey.description,
                'survey_type': survey.survey_type,
                'status': survey.status,
                'start_date': survey.start_date,
                'end_date': survey.end_date,
                'question_count': survey.questions.count(),
                'response_count': total_responses,
                'team_size': team_size,
                'completion_rate': round((total_responses / team_size * 100), 2) if team_size > 0 else 0,
                'is_active': survey.is_active,
                'created_at': survey.created_at
            }
            survey_data.append(survey_info)
        
        # Apply pagination
        paginator = StandardResultsSetPagination()
        paginated_surveys = paginator.paginate_queryset(survey_data, request)
        
        return paginator.get_paginated_response({
            'surveys': paginated_surveys,
            'summary': {
                'total_published': len(survey_data),
                'active_surveys': len([s for s in survey_data if s['status'] == 'active']),
                'team_size': User.objects.filter(employee_profile__manager=user).count()
            }
        })


class SurveyManagementAPIView(APIView):
    """API for managers to create and manage surveys (legacy endpoint)"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request, survey_id=None):
        """Get surveys created by the manager or detailed survey stats"""
        if survey_id:
            return self.get_survey_details(request, survey_id)
        
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        surveys = Survey.objects.filter(
            created_by=user
        ).annotate(
            total_responses=Count('responses'),
            completed_responses=Count('responses', filter=Q(responses__is_completed=True))
        ).order_by('-created_at')
        
        survey_data = []
        for survey in surveys:
            target_employees = survey.get_target_employees() if hasattr(survey, 'get_target_employees') else []
            target_count = len(target_employees)
            
            # Calculate completion rate
            completion_rate = 0
            if target_count > 0:
                completion_rate = round((survey.completed_responses / target_count) * 100)
            
            # Determine survey status for UI
            ui_status = 'active'
            if survey.status == 'closed':
                ui_status = 'closed'
            elif not survey.is_active:
                ui_status = 'expired'
            
            survey_info = {
                'id': survey.id,
                'title': survey.title,
                'description': survey.description,
                'survey_type': survey.survey_type,
                'status': survey.status,
                'ui_status': ui_status,
                'target_audience': survey.target_audience,
                'start_date': survey.start_date.isoformat() if survey.start_date else None,
                'end_date': survey.end_date.isoformat() if survey.end_date else None,
                'created_at': survey.created_at.isoformat() if survey.created_at else None,
                'is_anonymous': survey.is_anonymous,
                'total_responses': survey.total_responses,
                'completed_responses': survey.completed_responses,
                'pending_responses': survey.total_responses - survey.completed_responses,
                'target_employees_count': target_count,
                'completion_rate': completion_rate,
                'is_active': survey.is_active,
                'question_count': survey.questions.count() if hasattr(survey, 'questions') else 0
            }
            survey_data.append(survey_info)
        
        # Apply pagination
        paginator = StandardResultsSetPagination()
        paginated_surveys = paginator.paginate_queryset(survey_data, request)
        
        return paginator.get_paginated_response({
            'surveys': paginated_surveys,
            'total_surveys': len(survey_data)
        })
    
    def get_survey_details(self, request, survey_id):
        """Get detailed survey statistics for dashboard"""
        user = request.user
        
        try:
            survey = Survey.objects.get(id=survey_id, created_by=user)
        except Survey.DoesNotExist:
            return Response({
                'error': 'Survey not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get all responses and answers
        responses = SurveyResponse.objects.filter(survey=survey)
        completed_responses = responses.filter(is_completed=True)
        
        # Get target employees
        target_employees = survey.get_target_employees()
        target_count = len(target_employees)
        
        # Calculate completion rate
        completion_rate = 0
        if target_count > 0:
            completion_rate = round((completed_responses.count() / target_count) * 100)
        
        # Get question statistics
        questions_stats = []
        for question in survey.questions.all():
            answers = SurveyAnswer.objects.filter(
                question=question,
                response__is_completed=True
            )
            
            question_stat = {
                'id': question.id,
                'question_text': question.question_text,
                'question_type': question.question_type,
                'total_answers': answers.count(),
                'answer_distribution': {}
            }
            
            # Calculate answer distribution for rating questions
            if question.question_type == 'rating':
                for rating in range(1, 6):  # 1-5 rating scale
                    count = answers.filter(answer_rating=rating).count()
                    percentage = round((count / answers.count()) * 100) if answers.count() > 0 else 0
                    question_stat['answer_distribution'][str(rating)] = {
                        'count': count,
                        'percentage': percentage
                    }
            
            # Calculate answer distribution for choice questions
            elif question.question_type == 'choice':
                if question.choices:
                    for choice in question.choices:
                        count = answers.filter(answer_choice=choice).count()
                        percentage = round((count / answers.count()) * 100) if answers.count() > 0 else 0
                        question_stat['answer_distribution'][choice] = {
                            'count': count,
                            'percentage': percentage
                        }
            
            # Calculate answer distribution for boolean questions
            elif question.question_type == 'boolean':
                for bool_val in [True, False]:
                    count = answers.filter(answer_boolean=bool_val).count()
                    percentage = round((count / answers.count()) * 100) if answers.count() > 0 else 0
                    label = 'Yes' if bool_val else 'No'
                    question_stat['answer_distribution'][label] = {
                        'count': count,
                        'percentage': percentage
                    }
            
            questions_stats.append(question_stat)
        
        # Get pending team members
        pending_members = []
        if survey.target_audience == 'team':
            team_members = User.objects.filter(employee_profile__manager=user)
            completed_user_ids = completed_responses.values_list('respondent_id', flat=True)
            
            for member in team_members:
                if member.id not in completed_user_ids:
                    try:
                        profile = member.employee_profile
                        pending_members.append({
                            'id': member.id,
                            'name': f"{member.first_name} {member.last_name}",
                            'email': member.email,
                            'department': getattr(profile, 'department', 'Unknown'),
                            'status': 'pending'
                        })
                    except:
                        continue
        
        return Response({
            'survey': {
                'id': survey.id,
                'title': survey.title,
                'description': survey.description,
                'survey_type': survey.survey_type,
                'status': survey.status,
                'ui_status': 'closed' if survey.status == 'closed' else ('expired' if not survey.is_active else 'active'),
                'created_at': survey.created_at.isoformat(),
                'start_date': survey.start_date.isoformat() if survey.start_date else None,
                'end_date': survey.end_date.isoformat() if survey.end_date else None,
                'is_active': survey.is_active,
                'question_count': survey.questions.count()
            },
            'statistics': {
                'total_responses': responses.count(),
                'completed_responses': completed_responses.count(),
                'pending_responses': responses.filter(is_completed=False).count(),
                'target_employees_count': target_count,
                'completion_rate': completion_rate
            },
            'questions_stats': questions_stats,
            'pending_members': pending_members
        })
    
    def post(self, request):
        """Create a new survey"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Create survey
        survey_data = request.data
        survey = Survey.objects.create(
            title=survey_data.get('title'),
            description=survey_data.get('description'),
            survey_type=survey_data.get('survey_type'),
            created_by=user,
            target_audience=survey_data.get('target_audience', 'team'),
            start_date=survey_data.get('start_date'),
            end_date=survey_data.get('end_date'),
            is_anonymous=survey_data.get('is_anonymous', True)
        )
        
        # Create questions
        questions_data = survey_data.get('questions', [])
        for i, question_data in enumerate(questions_data):
            SurveyQuestion.objects.create(
                survey=survey,
                question_text=question_data.get('question_text'),
                question_type=question_data.get('question_type'),
                choices=question_data.get('choices'),
                is_required=question_data.get('is_required', True),
                order=i + 1
            )
        
        return Response({
            'message': 'Survey created successfully',
            'survey_id': survey.id
        }, status=status.HTTP_201_CREATED)
