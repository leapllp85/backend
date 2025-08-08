from rest_framework.permissions import BasePermission
from .models import EmployeeProfile


class IsManager(BasePermission):
    """
    Permission class to check if user is a manager.
    Managers are users who have other employees reporting to them.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            profile = request.user.employee_profile
            return profile.is_manager
        except EmployeeProfile.DoesNotExist:
            return False


class IsAssociate(BasePermission):
    """
    Permission class to check if user is an associate (any authenticated employee).
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            # Any user with an employee profile is an associate
            request.user.employee_profile
            return True
        except EmployeeProfile.DoesNotExist:
            return False


class IsManagerOrAssociate(BasePermission):
    """
    Permission class that allows access to both managers and associates.
    This is the base permission for most endpoints.
    """
    
    def has_permission(self, request, view):
        return IsAssociate().has_permission(request, view)


class IsOwnerOrManager(BasePermission):
    """
    Permission class that allows access to the owner of the resource or their manager.
    Useful for endpoints where users can access their own data or managers can access team data.
    """
    
    def has_permission(self, request, view):
        return IsAssociate().has_permission(request, view)
    
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            profile = request.user.employee_profile
            
            # If the object belongs to the user
            if hasattr(obj, 'user') and obj.user == request.user:
                return True
            elif hasattr(obj, 'employee') and obj.employee == request.user:
                return True
            
            # If the user is a manager and the object belongs to their team member
            if profile.is_manager:
                if hasattr(obj, 'user') and hasattr(obj.user, 'employee_profile'):
                    return obj.user.employee_profile.manager == request.user
                elif hasattr(obj, 'employee') and hasattr(obj.employee, 'employee_profile'):
                    return obj.employee.employee_profile.manager == request.user
            
            return False
        except EmployeeProfile.DoesNotExist:
            return False


class CanAccessTeamData(BasePermission):
    """
    Permission class for team-related endpoints.
    Allows managers to access their team data and associates to access their own data.
    """
    
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        try:
            profile = request.user.employee_profile
            # Managers can access team data, associates can access limited personal data
            return True
        except EmployeeProfile.DoesNotExist:
            return False
