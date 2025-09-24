from django.db.models import Q, Prefetch, Count, Avg
from django.db import connection
from django.core.cache import caches
import logging

logger = logging.getLogger(__name__)


def optimize_team_queries(queryset, user):
    """Optimize team-related queries with proper indexing and prefetching"""
    return queryset.select_related(
        'employee_profile',
        'employee_profile__manager'
    ).prefetch_related(
        Prefetch(
            'employee_allocations',
            queryset=ProjectAllocation.objects.select_related('project')
        )
    ).filter(employee_profile__manager=user)


def optimize_aggregation_query(model, filters, group_by_field, count_field='id'):
    """Optimized aggregation with proper indexing"""
    return model.objects.filter(
        **filters
    ).values(group_by_field).annotate(
        count=Count(count_field)
    ).order_by(group_by_field)


def get_team_analytics_optimized(user):
    """Optimized team analytics with single query"""
    from ..models import EmployeeProfile
    
    # Single query to get all needed data
    profiles = EmployeeProfile.objects.filter(
        manager=user
    ).select_related('user').values(
        'manager_assessment_risk',
        'mental_health',
        'age'
    )
    
    # Process in Python to avoid multiple DB hits
    total_members = len(profiles)
    if total_members == 0:
        return {
            'total_members': 0,
            'avg_mental_health_score': 0,
            'high_risk_count': 0,
            'avg_age': 0,
            'risk_distribution': {}
        }
    
    # Calculate metrics in memory
    risk_scores = {'High': 3, 'Medium': 2, 'Low': 1}
    mh_scores = [risk_scores.get(p['mental_health'], 2) for p in profiles]
    avg_mh_score = sum(mh_scores) / len(mh_scores)
    
    high_risk_count = sum(1 for p in profiles if p['manager_assessment_risk'] == 'High')
    
    ages = [p['age'] for p in profiles if p['age']]
    avg_age = sum(ages) / len(ages) if ages else 0
    
    # Risk distribution
    risk_dist = {}
    for p in profiles:
        risk = p['manager_assessment_risk']
        risk_dist[risk] = risk_dist.get(risk, 0) + 1
    
    return {
        'total_members': total_members,
        'avg_mental_health_score': round(avg_mh_score, 2),
        'high_risk_count': high_risk_count,
        'avg_age': round(avg_age, 1),
        'risk_distribution': risk_dist
    }


def log_query_performance(func):
    """Decorator to log query performance"""
    def wrapper(*args, **kwargs):
        initial_queries = len(connection.queries)
        result = func(*args, **kwargs)
        final_queries = len(connection.queries)
        
        logger.info(f"{func.__name__} executed {final_queries - initial_queries} queries")
        return result
    return wrapper


def bulk_prefetch_team_data(user_ids):
    """Bulk prefetch team data for multiple users"""
    from django.contrib.auth.models import User
    from ..models import EmployeeProfile, ProjectAllocation
    
    cache = caches['team_cache']
    
    # Check cache first
    cached_data = {}
    uncached_users = []
    
    for user_id in user_ids:
        cache_key = f"team_bulk:{user_id}"
        data = cache.get(cache_key)
        if data:
            cached_data[user_id] = data
        else:
            uncached_users.append(user_id)
    
    # Fetch uncached data
    if uncached_users:
        team_data = User.objects.filter(
            id__in=uncached_users
        ).select_related('employee_profile').prefetch_related(
            'employee_profile__team_members',
            'employee_profile__team_members__employee_allocations__project'
        )
        
        # Cache the results
        for user in team_data:
            cache_key = f"team_bulk:{user.id}"
            cache.set(cache_key, user, 300)
            cached_data[user.id] = user
    
    return cached_data
