from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.db.models import Sum, Q
from ..models import ProjectAllocation, Project
from ..serializers import ProjectAllocationSerializer
from datetime import datetime


class ProjectAllocationAPIView(APIView):
    """API for managing project allocations"""
    
    def get(self, request):
        """Get project allocations"""
        project_id = request.query_params.get('project_id')
        employee_id = request.query_params.get('employee_id')
        active_only = request.query_params.get('active_only', 'false').lower() == 'true'
        
        allocations = ProjectAllocation.objects.all()
        
        if project_id:
            allocations = allocations.filter(project_id=project_id)
        
        if employee_id:
            allocations = allocations.filter(employee_id=employee_id)
        
        if active_only:
            allocations = allocations.filter(is_active=True)
        
        allocations = allocations.select_related('employee', 'project')
        serializer = ProjectAllocationSerializer(allocations, many=True)
        return Response(serializer.data)
    
    def post(self, request):
        """Create new project allocation"""
        data = request.data
        
        # Validate that total allocation doesn't exceed 100%
        employee_id = data.get('employee')
        new_allocation = float(data.get('allocation_percentage', 0))
        
        if employee_id:
            existing_total = ProjectAllocation.objects.filter(
                employee_id=employee_id,
                is_active=True
            ).exclude(
                project_id=data.get('project')
            ).aggregate(
                total=Sum('allocation_percentage')
            )['total'] or 0
            
            if existing_total + new_allocation > 100:
                return Response({
                    'error': f'Total allocation would exceed 100%. Current: {existing_total}%, Trying to add: {new_allocation}%'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProjectAllocationSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def put(self, request, pk):
        """Update project allocation"""
        try:
            allocation = ProjectAllocation.objects.get(id=pk)
        except ProjectAllocation.DoesNotExist:
            return Response({'error': 'Allocation not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Validate allocation percentage if being updated
        if 'allocation_percentage' in request.data:
            new_allocation = float(request.data['allocation_percentage'])
            existing_total = ProjectAllocation.objects.filter(
                employee=allocation.employee,
                is_active=True
            ).exclude(id=pk).aggregate(
                total=Sum('allocation_percentage')
            )['total'] or 0
            
            if existing_total + new_allocation > 100:
                return Response({
                    'error': f'Total allocation would exceed 100%. Current other allocations: {existing_total}%, Trying to set: {new_allocation}%'
                }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = ProjectAllocationSerializer(allocation, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk):
        """Delete project allocation"""
        try:
            allocation = ProjectAllocation.objects.get(id=pk)
            allocation.delete()
            return Response({'message': 'Allocation deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
        except ProjectAllocation.DoesNotExist:
            return Response({'error': 'Allocation not found'}, status=status.HTTP_404_NOT_FOUND)


class ProjectTeamAPIView(APIView):
    """API for getting project team members and their allocations"""
    
    def get(self, request, project_id):
        """Get all team members for a specific project"""
        try:
            project = Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        
        allocations = ProjectAllocation.objects.filter(
            project=project,
            is_active=True
        ).select_related('employee', 'employee__employee_profile')
        
        team_data = []
        for allocation in allocations:
            employee = allocation.employee
            profile = getattr(employee, 'employee_profile', None)
            
            team_member = {
                'allocation_id': allocation.id,
                'employee_id': employee.id,
                'username': employee.username,
                'first_name': employee.first_name,
                'last_name': employee.last_name,
                'allocation_percentage': allocation.allocation_percentage,
                'start_date': allocation.start_date,
                'end_date': allocation.end_date,
                'profile_pic': profile.profile_pic if profile else None,
                'mental_health': profile.mental_health if profile else None,
                'suggested_risk': profile.suggested_risk if profile else None,
            }
            team_data.append(team_member)
        
        return Response({
            'project': {
                'id': project.id,
                'title': project.title,
                'status': project.status,
                'criticality': project.criticality
            },
            'team_members': team_data,
            'total_allocation': sum(member['allocation_percentage'] for member in team_data)
        })


class EmployeeAllocationSummaryAPIView(APIView):
    """API for getting employee allocation summary"""
    
    def get(self, request, employee_id):
        """Get allocation summary for a specific employee"""
        try:
            employee = User.objects.get(id=employee_id)
        except User.DoesNotExist:
            return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)
        
        active_allocations = ProjectAllocation.objects.filter(
            employee=employee,
            is_active=True
        ).select_related('project')
        
        allocation_data = []
        total_allocation = 0
        
        for allocation in active_allocations:
            allocation_data.append({
                'allocation_id': allocation.id,
                'project_id': allocation.project.id,
                'project_title': allocation.project.title,
                'project_status': allocation.project.status,
                'project_criticality': allocation.project.criticality,
                'allocation_percentage': allocation.allocation_percentage,
                'start_date': allocation.start_date,
                'end_date': allocation.end_date
            })
            total_allocation += allocation.allocation_percentage
        
        return Response({
            'employee': {
                'id': employee.id,
                'username': employee.username,
                'first_name': employee.first_name,
                'last_name': employee.last_name
            },
            'allocations': allocation_data,
            'total_allocation': total_allocation,
            'available_capacity': 100 - total_allocation
        })
