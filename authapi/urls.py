from django.urls import path
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from .views import RegisterUserView, ProfileView, EmployeeDesignationView, CustomTokenObtainPairView, LogoutAPIView, UserProfileAPIView

urlpatterns = [
    # Custom JWT token endpoints with role-based authentication
    path('login/', CustomTokenObtainPairView.as_view(), name='login'),
    path('logout/', LogoutAPIView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # User management endpoints
    path('user/register/', RegisterUserView.as_view(), name='register_user'),
    path('user/profile/', UserProfileAPIView.as_view(), name='user_profile_role_based'),
    path('profile/', ProfileView.as_view(), name='user_profile_legacy'),
    path('employee/designation/', EmployeeDesignationView.as_view(), name='employee_designation'),
]
