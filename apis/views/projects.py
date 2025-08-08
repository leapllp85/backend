# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from ..models import Project, EmployeeProfile, ProjectAllocation
from django.contrib.auth.models import User
from django.db.models import Q
from ..serializers import ProjectSerializer, MyProjectsSerializer
from ..permissions import IsManagerOrAssociate, IsManager, CanAccessTeamData

class ProjectAPIView(APIView):
    """General project CRUD API - Available to all authenticated users"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    serializer_class = ProjectSerializer

    # GET (Single or All)
    def get(self, request):
        user = request.user
        project_id = request.query_params.get('project_id')
        
        # Get single project by ID
        if project_id:
            try:
                project = Project.objects.get(id=project_id)
                serializer = self.serializer_class(project)
                return Response(serializer.data)
            except Project.DoesNotExist:
                return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get all projects (for backward compatibility)
        # In a role-based system, this might need filtering based on user role
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # return projects assigned to user
        projects = user.projects.all()
        print(projects)
        serializer = self.serializer_class(projects, many=True)
        return Response({
            'projects': serializer.data,
            'user_info': {
                'name': f"{user.first_name} {user.last_name}",
                'role': user_profile.role,
                'is_manager': user_profile.is_manager
            }
        })

    def post(self, request):
        """Create new project - Manager role required"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to create projects.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = self.serializer_class(data=request.data)
        if serializer.is_valid():
            project = serializer.save()
            return Response({
                'message': 'Project created successfully',
                'data': serializer.data,
                'created_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': 'manager'
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        """Update project - Manager role required"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to update projects.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            project = Project.objects.get(id=pk)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(project, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Project updated successfully',
                'data': serializer.data,
                'updated_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': 'manager'
                }
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """Delete project - Manager role required"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to delete projects.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        try:
            project = Project.objects.get(id=pk)
            project_title = project.title  # Store title for response
            project.delete()
            return Response({
                'message': f'Project "{project_title}" deleted successfully',
                'deleted_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': 'manager'
                }
            }, status=status.HTTP_200_OK)
        except Project.DoesNotExist:
            return Response({'error': 'Project not found'}, status=status.HTTP_404_NOT_FOUND)


class MyProjectsAPIView(APIView):
    """API for users to view their assigned projects"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    
    def get(self, request):
        """Get projects assigned to the current user"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get projects where user has active allocations
        active_allocations = ProjectAllocation.objects.filter(
            employee=user,
            is_active=True
        ).select_related('project')
        
        projects = [allocation.project for allocation in active_allocations]
        
        # Use custom serializer with allocation info
        serializer = MyProjectsSerializer(projects, many=True, context={'user': user})
        
        # Calculate summary statistics
        total_allocation = sum(allocation.allocation_percentage for allocation in active_allocations)
        project_count = len(projects)
        
        # Group by criticality
        criticality_breakdown = {'High': 0, 'Medium': 0, 'Low': 0}
        for project in projects:
            criticality_breakdown[project.criticality] += 1
        
        return Response({
            'projects': serializer.data,
            'summary': {
                'total_projects': project_count,
                'total_allocation': total_allocation,
                'available_capacity': 100 - total_allocation,
                'criticality_breakdown': criticality_breakdown
            },
            'user_info': {
                'name': f"{user.first_name} {user.last_name}",
                'role': user_profile.role,
                'manager': f"{user_profile.manager.first_name} {user_profile.manager.last_name}" if user_profile.manager else None
            }
        })


class TeamProjectsAPIView(APIView):
    """API for users to view team/personal projects based on role"""
    permission_classes = [IsAuthenticated, CanAccessTeamData]
    
    def get(self, request):
        """Get projects for manager's team or user's own projects for associates"""
        user = request.user
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Get relevant projects based on user role
        if user_profile.is_manager:
            # Get team members
            team_members = User.objects.filter(employee_profile__manager=user)
            # Get all projects where team members are allocated
            team_projects = Project.objects.filter(
                allocations__employee__in=team_members,
                allocations__is_active=True
            ).distinct().prefetch_related('allocations__employee')
            scope = 'team'
        else:
            # Associates see only their own projects
            team_members = User.objects.filter(id=user.id)
            team_projects = Project.objects.filter(
                allocations__employee=user,
                allocations__is_active=True
            ).distinct().prefetch_related('allocations__employee')
            scope = 'personal'
        
        projects_data = []
        for project in team_projects:
            # Get team member allocations for this project
            team_allocations = project.allocations.filter(
                employee__in=team_members,
                is_active=True
            ).select_related('employee')
            
            team_members_info = []
            total_team_allocation = 0
            
            for allocation in team_allocations:
                team_members_info.append({
                    'employee_id': allocation.employee.id,
                    'employee_name': f"{allocation.employee.first_name} {allocation.employee.last_name}",
                    'allocation_percentage': allocation.allocation_percentage
                })
                total_team_allocation += allocation.allocation_percentage
            
            project_info = {
                'id': project.id,
                'title': project.title,
                'description': project.description,
                'status': project.status,
                'criticality': project.criticality,
                'start_date': project.start_date,
                'go_live_date': project.go_live_date,
                'team_members': team_members_info,
                'total_team_allocation': total_team_allocation,
                'team_member_count': len(team_members_info)
            }
            projects_data.append(project_info)
        
        # Calculate summary statistics
        total_projects = len(projects_data)
        active_projects = len([p for p in projects_data if p['status'] == 'Active'])
        high_criticality = len([p for p in projects_data if p['criticality'] == 'High'])
        
        return Response({
            'projects': projects_data,
            'summary': {
                'total_projects': total_projects,
                'active_projects': active_projects,
                'high_criticality_projects': high_criticality,
                'team_size': team_members.count()
            },
            'user_info': {
                'name': f"{user.first_name} {user.last_name}",
                'role': user_profile.role,
                'is_manager': user_profile.is_manager,
                'scope': scope,
                'team_size': team_members.count() if user_profile.is_manager else 1
            }
        })
