from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db.models import Q
from ..permissions import IsManagerOrAssociate


class UserSearchAPIView(APIView):
    """API for searching users in the organization"""
    permission_classes = [IsManagerOrAssociate]
    
    def get(self, request):
        """Search users by name or username"""
        query = request.query_params.get('q', '').strip()
        limit = int(request.query_params.get('limit', 20))
        
        if not query:
            # Return all users if no query provided
            users = User.objects.filter(is_active=True).select_related('employee_profile')[:limit]
        else:
            # Search by first name, last name, or username
            users = User.objects.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query) |
                Q(username__icontains=query),
                is_active=True
            ).select_related('employee_profile')[:limit]
        
        user_data = []
        for user in users:
            profile = getattr(user, 'employee_profile', None)
            user_info = {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'full_name': f"{user.first_name} {user.last_name}".strip(),
                'email': user.email,
                'profile_pic': profile.profile_pic if profile else None,
                'is_manager': profile.is_manager if profile else False,
            }
            user_data.append(user_info)
        
        return Response({
            'users': user_data,
            'count': len(user_data)
        })
