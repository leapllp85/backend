from django.contrib.auth.models import User
from rest_framework import generics, views
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate, login, logout
from .models import EmployeeDesignation, Profile
from .serializers import UserRegistrationSerializer, ProfileSerializer, EmployeeDesignationSerializer
from apis.models import EmployeeProfile
from apis.serializers import EmployeeProfileSerializer
from apis.permissions import IsManagerOrAssociate

class RegisterUserView(generics.CreateAPIView):
    serializer_class = UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {"message": f"User {user.username} created successfully."},
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(views.APIView):

    permission_classes = [IsAuthenticated]
    serializer_class = ProfileSerializer

    def post(self, request, *args, **kwargs):
        """
        Create a profile for a user.

        Args:
            request (Request): The request being processed.

        Returns:
            Response: A response object containing the result of the request.
        """
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, *args, **kwargs):
        username = request.data.get("username")
        if not username:
            return Response({"error": "Username is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            profile = Profile.objects.get(user=user)
        except Profile.DoesNotExist:
            return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        username = request.query_params.get("username")
        if not username:
            return Response({"error": "Username is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            profile = Profile.objects.get(user=user)
        except Profile.DoesNotExist:
            return Response({"error": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.serializer_class(profile)
        return Response(serializer.data)


class EmployeeDesignationView(views.APIView):
    serializer_class = EmployeeDesignationSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request, *args, **kwargs):
        designations = EmployeeDesignation.objects.all()
        serializer = self.serializer_class(designations, many=True)
        return Response(serializer.data)


class UpdateEmployeeSupervisor(views.APIView):
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]

    def put(self, request, *args, **kwargs):
        username = request.data.get("username")
        if not username:
            return Response({"error": "Username is required."}, status=status.HTTP_400_BAD_REQUEST)
        if "supervisor" not in request.data:
            return Response({"error": "Supervisor field is required."}, status=status.HTTP_400_BAD_REQUEST)
        if "supervisor" in request.data and request.data["supervisor"] == "":
            return Response({"error": "Supervisor field cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)
        supervisor_username = request.data.pop('supervisor')
        try:
            supervisor = User.objects.get(username=supervisor_username)
        except User.DoesNotExist:
            return Response({"error": "Supervisor not found."}, status=status.HTTP_404_NOT_FOUND)
        profile = Profile.objects.get(user__username=username)
        serializer = ProfileSerializer(profile, data={"supervisor": supervisor}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Custom Role-Based Authentication Views
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
                    'manager': f"{profile.manager.first_name} {profile.manager.last_name}" if profile.manager else None,
                    'profile_pic': profile.profile_pic,
                    'permissions': self.get_user_permissions(profile.role, profile.is_manager)
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
                    'manager': None,
                    'profile_pic': None,
                    'permissions': self.get_user_permissions('associate', False)
                }
            })
        
        return data
    
    def get_user_permissions(self, role, is_manager):
        """Get user permissions based on role"""
        base_permissions = ['chat', 'profile', 'surveys', 'my_projects']
        
        if is_manager:
            manager_permissions = ['team_dashboard', 'team_projects', 'my_team', 'survey_management']
            return base_permissions + manager_permissions
        
        return base_permissions


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token view with role-based authentication"""
    serializer_class = CustomTokenObtainPairSerializer


class LogoutAPIView(APIView):
    """Logout API"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get('refresh_token')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({
                'message': 'Successfully logged out'
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'error': 'Invalid token or logout failed'
            }, status=status.HTTP_400_BAD_REQUEST)


class UserProfileAPIView(APIView):
    """API to get current user profile with role information"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    
    def get(self, request):
        user = request.user
        try:
            profile = user.employee_profile
            serializer = EmployeeProfileSerializer(profile)
            
            return Response({
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'role': profile.role,
                    'is_manager': profile.is_manager,
                    'manager': f"{profile.manager.first_name} {profile.manager.last_name}" if profile.manager else None,
                    'profile_pic': profile.profile_pic,
                    'permissions': self.get_user_permissions(profile.role, profile.is_manager)
                },
                'profile': serializer.data
            })
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
    
    def get_user_permissions(self, role, is_manager):
        """Get user permissions based on role"""
        base_permissions = ['chat', 'profile', 'surveys', 'my_projects']
        
        if is_manager:
            manager_permissions = ['team_dashboard', 'team_projects', 'my_team', 'survey_management']
            return base_permissions + manager_permissions
        
        return base_permissions
