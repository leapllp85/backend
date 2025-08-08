from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from ..models import EmployeeProfile
from ..serializers import EmployeeProfileSerializer
from ..permissions import IsManagerOrAssociate


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom JWT token serializer that includes user role and profile info"""
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Add custom claims
        try:
            profile = user.employee_profile
            token['role'] = profile.role
            token['is_manager'] = profile.is_manager
            token['user_id'] = user.id
            token['username'] = user.username
            token['first_name'] = user.first_name
            token['last_name'] = user.last_name
        except EmployeeProfile.DoesNotExist:
            token['role'] = 'associate'
            token['is_manager'] = False
            token['user_id'] = user.id
            token['username'] = user.username
            token['first_name'] = user.first_name
            token['last_name'] = user.last_name
        
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add user profile information to response
        user = self.user
        try:
            profile = user.employee_profile
            data.update({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'role': profile.role,
                    'is_manager': profile.is_manager,
                    'profile_pic': profile.profile_pic,
                    'manager_id': profile.manager.id if profile.manager else None,
                    'manager_name': f"{profile.manager.first_name} {profile.manager.last_name}" if profile.manager else None
                }
            })
        except EmployeeProfile.DoesNotExist:
            data.update({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'role': 'associate',
                    'is_manager': False,
                    'profile_pic': None,
                    'manager_id': None,
                    'manager_name': None
                }
            })
        
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token view with role-based authentication"""
    serializer_class = CustomTokenObtainPairSerializer


class LoginAPIView(APIView):
    """Role-based login API"""
    
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        
        if not username or not password:
            return Response({
                'error': 'Username and password are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Authenticate user
        user = authenticate(username=username, password=password)
        
        if not user:
            return Response({
                'error': 'Invalid credentials'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        if not user.is_active:
            return Response({
                'error': 'Account is disabled'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        access_token = refresh.access_token
        
        # Get user profile and role
        try:
            profile = user.employee_profile
            role = profile.role
            is_manager = profile.is_manager
            team_count = profile.get_team_members().count() if is_manager else 0
        except EmployeeProfile.DoesNotExist:
            # Create basic profile if doesn't exist
            profile = EmployeeProfile.objects.create(
                user=user,
                age=30,  # Default age
            )
            role = 'associate'
            is_manager = False
            team_count = 0
        
        return Response({
            'access': str(access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'role': role,
                'is_manager': is_manager,
                'team_count': team_count,
                'profile_pic': profile.profile_pic,
                'manager_id': profile.manager.id if profile.manager else None,
                'manager_name': f"{profile.manager.first_name} {profile.manager.last_name}" if profile.manager else None
            },
            'permissions': self.get_user_permissions(role, is_manager)
        }, status=status.HTTP_200_OK)
    
    def get_user_permissions(self, role, is_manager):
        """Get user permissions based on role"""
        base_permissions = [
            'chat',
            'profile',
            'surveys',
            'my_projects'
        ]
        
        manager_permissions = [
            'team_dashboard',
            'team_projects',
            'my_team',
            'team_analytics',
            'project_allocations'
        ]
        
        if is_manager:
            return base_permissions + manager_permissions
        
        return base_permissions


class LogoutAPIView(APIView):
    """Logout API"""
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileAPIView(APIView):
    """API to get current user profile with role information"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    
    def get(self, request):
        user = request.user
        try:
            profile = user.employee_profile
            serializer = EmployeeProfileSerializer(profile)
            
            # Add role-specific data
            profile_data = serializer.data
            profile_data.update({
                'role': profile.role,
                'is_manager': profile.is_manager,
                'team_count': profile.get_team_members().count() if profile.is_manager else 0,
                'permissions': self.get_user_permissions(profile.role, profile.is_manager)
            })
            
            return Response(profile_data)
            
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def get_user_permissions(self, role, is_manager):
        """Get user permissions based on role"""
        base_permissions = [
            'chat',
            'profile',
            'surveys',
            'my_projects'
        ]
        
        manager_permissions = [
            'team_dashboard',
            'team_projects',
            'my_team',
            'team_analytics',
            'project_allocations'
        ]
        
        if is_manager:
            return base_permissions + manager_permissions
        
        return base_permissions
