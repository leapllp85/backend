from django.http import JsonResponse
from django.db import connection
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import logging

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class HealthCheckView(View):
    """
    Health check endpoint for Docker container monitoring
    """
    
    def get(self, request, *args, **kwargs):
        """
        Perform health checks and return status
        """
        health_status = {
            'status': 'healthy',
            'checks': {
                'database': 'unknown',
                'application': 'healthy'
            }
        }
        
        # Check database connection
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                health_status['checks']['database'] = 'healthy'
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            health_status['checks']['database'] = 'unhealthy'
            health_status['status'] = 'unhealthy'
        
        # Return appropriate HTTP status code
        status_code = 200 if health_status['status'] == 'healthy' else 503
        
        return JsonResponse(health_status, status=status_code)
