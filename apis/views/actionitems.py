from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q
from ..models import ActionItem, Survey, SurveyResponse, EmployeeProfile
from ..serializers import ActionItemSerializer
from ..permissions import IsManagerOrAssociate, IsManager

class ActionItemAPIView(APIView):
    """Enhanced Action Items API with survey integration"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    serializer_class = ActionItemSerializer

    def get(self, request):
        """Get action items for the current user, including survey-based action items"""
        user = request.user
        user_id = request.query_params.get('user_id')
        status_filter = request.query_params.get('status')
        
        # If user_id is provided, use it (for backward compatibility)
        if user_id:
            try:
                target_user = User.objects.get(username=user_id)
            except User.DoesNotExist:
                return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            target_user = user
        
        # Get regular action items
        action_items_query = ActionItem.objects.filter(assigned_to=target_user)
        if status_filter:
            action_items_query = action_items_query.filter(status=status_filter)
        
        action_items = list(action_items_query)
        
        # Get survey-based action items
        survey_action_items = self.get_survey_action_items(target_user, status_filter)
        
        # Combine both types of action items
        all_action_items = action_items + survey_action_items
        
        # Serialize and return
        serializer = self.serializer_class(all_action_items, many=True)
        return Response({
            'action_items': serializer.data,
            'summary': {
                'total_items': len(all_action_items),
                'regular_items': len(action_items),
                'survey_items': len(survey_action_items),
                'user': target_user.username
            }
        })
    
    def get_survey_action_items(self, user, status_filter=None):
        """Generate action items for pending surveys"""
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return []
        
        # Get active surveys that user hasn't completed
        now = timezone.now()
        available_surveys = Survey.objects.filter(
            status='active',
            start_date__lte=now,
            end_date__gte=now
        )
        
        # Filter surveys based on target audience
        team_surveys = []
        for survey in available_surveys:
            if survey.target_audience == 'all':
                team_surveys.append(survey)
            elif survey.target_audience == 'team' and user_profile.manager:
                # Check if survey was created by user's manager
                if survey.created_by == user_profile.manager:
                    team_surveys.append(survey)
        
        # Check which surveys user has already completed
        completed_survey_ids = SurveyResponse.objects.filter(
            respondent=user,
            is_completed=True
        ).values_list('survey_id', flat=True)
        
        # Create action items for pending surveys
        survey_action_items = []
        for survey in team_surveys:
            if survey.id not in completed_survey_ids:
                # Create a virtual action item for the survey
                action_item = ActionItem(
                    id=survey.id,
                    assigned_to=user,
                    title=f"Complete Survey: {survey.title}",
                    status='Pending',
                    action=f"/surveys/{survey.id}",  # Frontend route
                    created_at=survey.created_at,
                    updated_at=survey.updated_at
                )
                
                # Apply status filter if provided
                if not status_filter or action_item.status == status_filter:
                    survey_action_items.append(action_item)
        
        return survey_action_items

    # POST (Create) - Manager only
    def post(self, request):
        """Create new action items - Manager role required"""
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
                'error': 'Access denied. Manager role required to assign action items.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Handle both single and multiple action items
        data = request.data
        is_many = isinstance(data, list)
        
        serializer = self.serializer_class(data=data, many=is_many)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': f'{"Action items" if is_many else "Action item"} created successfully',
                'data': serializer.data,
                'created_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': 'manager'
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # PUT (Update) - Manager only for assignment changes
    def put(self, request, pk):
        """Update action items - Manager role required for assignment changes"""
        user = request.user
        
        try:
            action_item = ActionItem.objects.get(id=pk)
        except ActionItem.DoesNotExist:
            return Response({'error': 'ActionItem not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if this is an assignment change (changing assigned_to field)
        if 'assigned_to' in request.data and not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to reassign action items.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Allow users to update their own action item status
        if action_item.assigned_to != user and not user_profile.is_manager:
            return Response({
                'error': 'Access denied. You can only update your own action items.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = self.serializer_class(action_item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Action item updated successfully',
                'data': serializer.data,
                'updated_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': user_profile.role
                }
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # DELETE - Manager only
    def delete(self, request, pk):
        """Delete action items - Manager role required"""
        user = request.user
        
        try:
            action_item = ActionItem.objects.get(id=pk)
        except ActionItem.DoesNotExist:
            return Response({'error': 'ActionItem not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to delete action items.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        action_item.delete()
        return Response({
            'message': 'Action item deleted successfully',
            'deleted_by': {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'role': 'manager'
            }
        }, status=status.HTTP_200_OK)
