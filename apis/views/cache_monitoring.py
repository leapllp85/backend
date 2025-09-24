from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.core.cache import caches
from django.contrib.auth.models import User
from apis.permissions import IsManager
from apis.models import EmployeeProfile
from apis.signals import invalidate_all_team_caches
from apis.utils.cache_utils import invalidate_user_cache
import logging

logger = logging.getLogger(__name__)


class CacheMonitoringAPIView(APIView):
    """API for monitoring and managing cache performance"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def get(self, request):
        """Get cache statistics and health information"""
        try:
            stats = {
                'team_cache': self._get_cache_stats('team_cache'),
                'default_cache': self._get_cache_stats('default'),
                'cache_health': self._check_cache_health(),
                'active_users': self._get_active_users_count(),
                'cache_keys_count': self._count_cache_keys()
            }
            
            return Response({
                'success': True,
                'cache_stats': stats,
                'timestamp': request.META.get('HTTP_X_TIMESTAMP')
            })
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request):
        """Clear specific or all caches"""
        cache_type = request.query_params.get('type', 'all')
        user_id = request.query_params.get('user_id')
        
        try:
            if user_id:
                # Clear cache for specific user
                invalidate_user_cache(int(user_id))
                message = f"Cache cleared for user ID: {user_id}"
                
            elif cache_type == 'team':
                # Clear only team cache
                team_cache = caches['team_cache']
                team_cache.clear()
                message = "Team cache cleared"
                
            elif cache_type == 'default':
                # Clear only default cache
                default_cache = caches['default']
                default_cache.clear()
                message = "Default cache cleared"
                
            else:
                # Clear all caches
                result = invalidate_all_team_caches()
                if result:
                    message = "All caches cleared successfully"
                else:
                    raise Exception("Failed to clear all caches")
            
            logger.info(f"Cache management action: {message} by user {request.user.username}")
            
            return Response({
                'success': True,
                'message': message,
                'cleared_at': request.META.get('HTTP_X_TIMESTAMP')
            })
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _get_cache_stats(self, cache_name):
        """Get statistics for a specific cache"""
        try:
            cache = caches[cache_name]
            
            # Basic cache info
            stats = {
                'name': cache_name,
                'backend': str(type(cache)),
                'available': True
            }
            
            # Redis-specific stats
            if hasattr(cache, '_cache') and hasattr(cache._cache, 'info'):
                try:
                    redis_info = cache._cache.info()
                    stats.update({
                        'used_memory': redis_info.get('used_memory_human', 'N/A'),
                        'connected_clients': redis_info.get('connected_clients', 0),
                        'keyspace_hits': redis_info.get('keyspace_hits', 0),
                        'keyspace_misses': redis_info.get('keyspace_misses', 0),
                        'total_commands_processed': redis_info.get('total_commands_processed', 0),
                        'uptime_in_seconds': redis_info.get('uptime_in_seconds', 0)
                    })
                    
                    # Calculate hit rate
                    hits = redis_info.get('keyspace_hits', 0)
                    misses = redis_info.get('keyspace_misses', 0)
                    total = hits + misses
                    hit_rate = (hits / total * 100) if total > 0 else 0
                    stats['hit_rate_percentage'] = round(hit_rate, 2)
                    
                except Exception as redis_error:
                    stats['redis_error'] = str(redis_error)
            
            return stats
            
        except Exception as e:
            return {
                'name': cache_name,
                'available': False,
                'error': str(e)
            }
    
    def _check_cache_health(self):
        """Check overall cache health"""
        try:
            # Test cache operations
            test_key = 'health_check_test'
            test_value = 'test_data'
            
            # Test team cache
            team_cache = caches['team_cache']
            team_cache.set(test_key, test_value, 10)
            team_result = team_cache.get(test_key) == test_value
            team_cache.delete(test_key)
            
            # Test default cache
            default_cache = caches['default']
            default_cache.set(test_key, test_value, 10)
            default_result = default_cache.get(test_key) == test_value
            default_cache.delete(test_key)
            
            return {
                'overall_health': 'healthy' if (team_result and default_result) else 'degraded',
                'team_cache_operational': team_result,
                'default_cache_operational': default_result,
                'last_checked': request.META.get('HTTP_X_TIMESTAMP')
            }
            
        except Exception as e:
            return {
                'overall_health': 'unhealthy',
                'error': str(e),
                'last_checked': request.META.get('HTTP_X_TIMESTAMP')
            }
    
    def _get_active_users_count(self):
        """Get count of users with active cache entries"""
        try:
            # Count users with employee profiles (potential cache users)
            total_users = User.objects.filter(employee_profile__isnull=False).count()
            managers = EmployeeProfile.objects.filter(is_manager=True).count()
            associates = total_users - managers
            
            return {
                'total_users': total_users,
                'managers': managers,
                'associates': associates
            }
            
        except Exception as e:
            logger.error(f"Error getting active users count: {e}")
            return {
                'total_users': 0,
                'managers': 0,
                'associates': 0,
                'error': str(e)
            }
    
    def _count_cache_keys(self):
        """Count approximate number of cache keys"""
        try:
            counts = {}
            
            # Team cache keys
            try:
                team_cache = caches['team_cache']
                if hasattr(team_cache, '_cache') and hasattr(team_cache._cache, 'dbsize'):
                    counts['team_cache_keys'] = team_cache._cache.dbsize()
                else:
                    counts['team_cache_keys'] = 'N/A'
            except Exception:
                counts['team_cache_keys'] = 'Error'
            
            # Default cache keys (approximate)
            try:
                default_cache = caches['default']
                if hasattr(default_cache, '_cache') and hasattr(default_cache._cache, 'dbsize'):
                    counts['default_cache_keys'] = default_cache._cache.dbsize()
                else:
                    counts['default_cache_keys'] = 'N/A'
            except Exception:
                counts['default_cache_keys'] = 'Error'
            
            return counts
            
        except Exception as e:
            logger.error(f"Error counting cache keys: {e}")
            return {
                'team_cache_keys': 'Error',
                'default_cache_keys': 'Error',
                'error': str(e)
            }


class CacheInvalidationAPIView(APIView):
    """API for manual cache invalidation operations"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def post(self, request):
        """Manually trigger cache invalidation for specific scenarios"""
        operation = request.data.get('operation')
        target_id = request.data.get('target_id')
        
        try:
            if operation == 'invalidate_user':
                if not target_id:
                    return Response({
                        'success': False,
                        'error': 'target_id required for user invalidation'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                invalidate_user_cache(target_id)
                message = f"Cache invalidated for user ID: {target_id}"
                
            elif operation == 'invalidate_team':
                if not target_id:
                    return Response({
                        'success': False,
                        'error': 'target_id (manager_id) required for team invalidation'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Invalidate cache for manager and all team members
                manager = User.objects.get(id=target_id)
                invalidate_user_cache(manager.id)
                
                team_members = EmployeeProfile.objects.filter(
                    manager=manager
                ).values_list('user_id', flat=True)
                
                for member_id in team_members:
                    invalidate_user_cache(member_id)
                
                message = f"Cache invalidated for manager {target_id} and {len(team_members)} team members"
                
            elif operation == 'invalidate_all':
                result = invalidate_all_team_caches()
                if result:
                    message = "All team caches invalidated successfully"
                else:
                    raise Exception("Failed to invalidate all caches")
                
            else:
                return Response({
                    'success': False,
                    'error': 'Invalid operation. Use: invalidate_user, invalidate_team, or invalidate_all'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            logger.info(f"Manual cache invalidation: {message} by user {request.user.username}")
            
            return Response({
                'success': True,
                'message': message,
                'operation': operation,
                'target_id': target_id,
                'timestamp': request.META.get('HTTP_X_TIMESTAMP')
            })
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'error': f'User with ID {target_id} not found'
            }, status=status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            logger.error(f"Error in manual cache invalidation: {e}")
            return Response({
                'success': False,
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
