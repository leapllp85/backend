from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from apis.permissions import IsManager
from django.core.cache import cache
from django.utils import timezone
import logging
import time

logger = logging.getLogger(__name__)

class CacheManagementView(APIView):
    """API for managing LLM response cache with granular control"""
    permission_classes = [IsAuthenticated]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache_prefix = 'llm_chat'
    
    def get(self, request, *args, **kwargs):
        """Get cache statistics for the current user"""
        try:
            from .llm import ChatAPIView
            chat_view = ChatAPIView()
            
            stats = chat_view.get_cache_stats(request.user.username)
            
            return JsonResponse({
                "success": True,
                "cache_stats": stats,
                "user": request.user.username
            })
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return JsonResponse({
                "error": f"Error retrieving cache statistics: {str(e)}",
                "success": False
            }, status=500)
    
    def delete(self, request, *args, **kwargs):
        """Clear cache for the current user"""
        try:
            from .llm import ChatAPIView
            chat_view = ChatAPIView()
            
            # Invalidate user's cache
            chat_view.invalidate_user_cache(request.user.username)
            
            return JsonResponse({
                "success": True,
                "message": f"Cache cleared for user {request.user.username}"
            })
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return JsonResponse({
                "error": f"Error clearing cache: {str(e)}",
                "success": False
            }, status=500)


class AdminCacheManagementView(APIView):
    """Admin API for managing system-wide cache"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cache_prefix = 'llm_chat'
    
    def get(self, request, *args, **kwargs):
        """Get system-wide cache statistics"""
        try:
            # Get all cache keys with our prefix
            # Note: This is a simplified approach. In production, you might want to use Redis SCAN
            stats = {
                "cache_info": "System cache statistics",
                "timestamp": timezone.now().isoformat(),
                "note": "Detailed cache analysis requires Redis direct access"
            }
            
            return JsonResponse({
                "success": True,
                "system_cache_stats": stats
            })
            
        except Exception as e:
            logger.error(f"Error getting system cache stats: {e}")
            return JsonResponse({
                "error": f"Error retrieving system cache statistics: {str(e)}",
                "success": False
            }, status=500)
    
    def delete(self, request, *args, **kwargs):
        """Clear system-wide LLM cache (admin only)"""
        try:
            # Clear all LLM cache keys
            # This is a simplified approach - in production you'd want to use Redis SCAN
            cache.clear()
            
            logger.info(f"System cache cleared by admin user: {request.user.username}")
            
            return JsonResponse({
                "success": True,
                "message": "System-wide cache cleared successfully"
            })
            
        except Exception as e:
            logger.error(f"Error clearing system cache: {e}")
            return JsonResponse({
                "error": f"Error clearing system cache: {str(e)}",
                "success": False
            }, status=500)


def invalidate_cache_on_data_change(sender, instance, **kwargs):
    """Enhanced signal handler to invalidate specific cache keys when data changes"""
    try:
        from .llm import ChatAPIView
        chat_view = ChatAPIView()
        
        # Track affected users and specific cache types
        affected_users = set()
        cache_types_to_invalidate = set()
        
        if sender.__name__ == 'EmployeeProfile':
            # Employee profile changes affect:
            # 1. The employee's own cache
            # 2. Their manager's cache (team data)
            # 3. Any manager who has this employee in their team
            
            affected_users.add(instance.user.username)
            cache_types_to_invalidate.update(['context', 'responses'])
            
            # Invalidate manager's cache
            if instance.manager:
                affected_users.add(instance.manager.username)
            
            # Find all managers who might have this employee in their team context
            from apis.models import EmployeeProfile
            managers_with_this_employee = EmployeeProfile.objects.filter(
                manager=instance.user,
                is_manager=True
            ).values_list('user__username', flat=True)
            
            affected_users.update(managers_with_this_employee)
            
            logger.info(f"EmployeeProfile change for {instance.user.username} affects {len(affected_users)} users")
        
        elif sender.__name__ == 'ProjectAllocation':
            # Project allocation changes affect:
            # 1. The allocated employee
            # 2. Project managers
            # 3. Employee's manager
            
            affected_users.add(instance.employee.username)
            cache_types_to_invalidate.update(['context', 'responses'])
            
            # Get employee's manager
            try:
                employee_profile = instance.employee.employee_profile
                if employee_profile.manager:
                    affected_users.add(employee_profile.manager.username)
            except:
                pass
            
            # Get project-related managers (if project has manager info)
            # This would need to be expanded based on your project model structure
            
            logger.info(f"ProjectAllocation change affects {len(affected_users)} users")
        
        elif sender.__name__ == 'Project':
            # Project changes affect all allocated employees and their managers
            from apis.models import ProjectAllocation, EmployeeProfile
            
            allocations = ProjectAllocation.objects.filter(project=instance)
            for allocation in allocations:
                affected_users.add(allocation.employee.username)
                
                # Add employee's manager
                try:
                    employee_profile = allocation.employee.employee_profile
                    if employee_profile.manager:
                        affected_users.add(employee_profile.manager.username)
                except:
                    pass
            
            cache_types_to_invalidate.update(['context', 'responses'])
            logger.info(f"Project change for '{instance.title}' affects {len(affected_users)} users")
        
        elif sender.__name__ in ['Course', 'Survey']:
            # Global data changes - invalidate all manager caches since they see system-wide data
            from apis.models import EmployeeProfile
            manager_usernames = EmployeeProfile.objects.filter(
                is_manager=True
            ).values_list('user__username', flat=True)
            
            affected_users.update(manager_usernames)
            cache_types_to_invalidate.add('context')  # Only context, not all responses
            
            logger.info(f"{sender.__name__} change affects {len(affected_users)} manager users")
        
        elif sender.__name__ == 'ActionItem':
            # Action item changes affect:
            # 1. The assigned user
            # 2. The assigned user's manager
            
            if hasattr(instance, 'assigned_to') and instance.assigned_to:
                affected_users.add(instance.assigned_to.username)
                
                # Add assigned user's manager
                try:
                    employee_profile = instance.assigned_to.employee_profile
                    if employee_profile.manager:
                        affected_users.add(employee_profile.manager.username)
                except:
                    pass
            
            cache_types_to_invalidate.update(['context', 'responses'])
            logger.info(f"ActionItem change affects {len(affected_users)} users")
        
        # Perform granular cache invalidation
        invalidated_count = 0
        for username in affected_users:
            try:
                if 'context' in cache_types_to_invalidate:
                    # Invalidate context cache
                    chat_view.invalidate_user_context_cache(username)
                    invalidated_count += 1
                
                if 'responses' in cache_types_to_invalidate:
                    # Invalidate all response caches for this user
                    chat_view.invalidate_user_response_cache(username)
                    invalidated_count += 1
                    
            except Exception as e:
                logger.error(f"Error invalidating cache for user {username}: {e}")
        
        if invalidated_count > 0:
            logger.info(f"Successfully invalidated {invalidated_count} cache entries due to {sender.__name__} change")
                
    except Exception as e:
        logger.error(f"Error in enhanced cache invalidation signal handler: {e}")
