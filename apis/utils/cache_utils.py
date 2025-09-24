from django.core.cache import caches
from django.conf import settings
import hashlib
import json
from functools import wraps
from django.http import JsonResponse
from rest_framework.response import Response


def generate_cache_key(prefix, user_id, **kwargs):
    """Generate a cache key based on prefix, user_id and additional parameters"""
    key_data = {
        'user_id': user_id,
        **kwargs
    }
    key_string = json.dumps(key_data, sort_keys=True)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()
    return f"{prefix}:{key_hash}"


def cache_team_data(timeout=300):
    """Decorator to cache team-related API responses"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            try:
                # Get cache instance with fallback
                cache = caches['team_cache']
            except Exception:
                # Fallback to default cache if team_cache fails
                try:
                    cache = caches['default']
                except Exception:
                    # If all caches fail, skip caching and execute view directly
                    return view_func(self, request, *args, **kwargs)
            
            # Generate cache key based on user and query parameters
            user_id = request.user.id
            query_params = dict(request.GET.items())
            
            cache_key = generate_cache_key(
                f"team_api:{view_func.__name__}",
                user_id,
                **query_params
            )
            
            # Try to get from cache
            try:
                cached_response = cache.get(cache_key)
                if cached_response:
                    return Response(cached_response)
            except Exception:
                # Cache read failed, continue without cache
                pass
            
            # Execute the view function
            response = view_func(self, request, *args, **kwargs)
            
            # Cache the response data if it's successful
            try:
                if hasattr(response, 'data') and response.status_code == 200:
                    cache.set(cache_key, response.data, timeout)
            except Exception:
                # Cache write failed, continue without caching
                pass
            
            return response
        return wrapper
    return decorator


def invalidate_user_cache(user_id, cache_patterns=None):
    """Invalidate all cache entries for a specific user"""
    try:
        cache = caches['team_cache']
    except Exception:
        try:
            cache = caches['default']
        except Exception:
            # If cache is unavailable, skip invalidation
            return
    
    if cache_patterns is None:
        cache_patterns = [
            'team_api:get',
            'team_analytics',
            'team_stats',
            'project_stats',
            'metrics',
            'attrition_graph',
            'distribution_graph'
        ]
    
    # Note: Redis doesn't support pattern deletion easily
    # This is a simplified approach - in production, consider using cache versioning
    for pattern in cache_patterns:
        try:
            cache_key = generate_cache_key(pattern, user_id)
            cache.delete(cache_key)
        except:
            pass  # Continue if key doesn't exist


def cache_aggregation_data(timeout=600):
    """Decorator specifically for aggregation queries with longer timeout"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(self, request, *args, **kwargs):
            try:
                cache = caches['default']
            except Exception:
                # If cache is unavailable, skip caching and execute view directly
                return view_func(self, request, *args, **kwargs)
            
            user_id = request.user.id
            query_params = dict(request.GET.items())
            
            cache_key = generate_cache_key(
                f"aggregation:{view_func.__name__}",
                user_id,
                **query_params
            )
            
            try:
                cached_response = cache.get(cache_key)
                if cached_response:
                    return Response(cached_response)
            except Exception:
                # Cache read failed, continue without cache
                pass
            
            response = view_func(self, request, *args, **kwargs)
            
            try:
                if hasattr(response, 'data') and response.status_code == 200:
                    cache.set(cache_key, response.data, timeout)
            except Exception:
                # Cache write failed, continue without caching
                pass
            
            return response
        return wrapper
    return decorator
