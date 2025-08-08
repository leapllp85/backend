from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth.models import User
from ..models import Course, CourseCategory, EmployeeProfile
from ..serializers import CourseSerializer, CourseCategorySerializer
from ..permissions import IsManagerOrAssociate, IsManager

class CourseAPIView(APIView):
    """Course API with role-based permissions: viewing for all, creating for managers"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]
    serializer_class = CourseSerializer

    def get(self, request):
        """Get courses - Available to all authenticated users"""
        course_id = request.query_params.get('course_id')
        category = request.query_params.get('category')
        
        try:
            if course_id:
                course = Course.objects.get(id=course_id)
                serializer = self.serializer_class(course)
                return Response({
                    'course': serializer.data,
                    'message': 'Course retrieved successfully'
                })
            elif category:
                courses = Course.objects.filter(category__name=category)
                serializer = self.serializer_class(courses, many=True)
                return Response({
                    'courses': serializer.data,
                    'category': category,
                    'count': courses.count()
                })
            else:
                # Return all courses if no specific filter
                courses = Course.objects.all().prefetch_related('category')
                serializer = self.serializer_class(courses, many=True)
                return Response({
                    'courses': serializer.data,
                    'total_count': courses.count(),
                    'message': 'All courses retrieved successfully'
                })
        except Course.DoesNotExist:
            return Response({
                'error': 'Course not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'error': f'Error retrieving courses: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        """Create new courses - Manager role required"""
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
                'error': 'Access denied. Manager role required to create courses.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Handle both single and multiple courses
        data = request.data
        is_many = isinstance(data, list)
        
        serializer = self.serializer_class(data=data, many=is_many)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': f'{"Courses" if is_many else "Course"} created successfully',
                'data': serializer.data,
                'created_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': 'manager'
                }
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        """Update courses - Manager role required"""
        user = request.user
        
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to update courses.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        serializer = self.serializer_class(course, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Course updated successfully',
                'data': serializer.data,
                'updated_by': {
                    'id': user.id,
                    'name': f"{user.first_name} {user.last_name}",
                    'role': 'manager'
                }
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """Delete courses - Manager role required"""
        user = request.user
        
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return Response({
                'error': 'Employee profile not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user is a manager
        if not user_profile.is_manager:
            return Response({
                'error': 'Access denied. Manager role required to delete courses.'
            }, status=status.HTTP_403_FORBIDDEN)
        
        course.delete()
        return Response({
            'message': 'Course deleted successfully',
            'deleted_by': {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'role': 'manager'
            }
        }, status=status.HTTP_200_OK)

class CourseCategoryAPIView(APIView):

    serializer_class = CourseCategorySerializer

    # GET (Single or All)
    def get(self, request):
        category_id = request.query_params.get('category_id')

        if category_id:
            course = CourseCategory.objects.get(id=category_id)
            serializer = self.serializer_class(course)
            return Response(serializer.data)
        else:
            courses = CourseCategory.objects.all()
            serializer = self.serializer_class(courses, many=True)
            return Response(serializer.data)

    def post(self, request):
        serializer = self.serializer_class(data=request.data, many=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def put(self, request, pk):
        try:
            course = CourseCategory.objects.get(id=pk)
        except CourseCategory.DoesNotExist:
            return Response({'error': 'CourseCategory not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.serializer_class(course, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        try:
            course = CourseCategory.objects.get(id=pk)
            course.delete()
            return Response({'message': 'CourseCategory deleted'}, status=status.HTTP_204_NO_CONTENT)
        except CourseCategory.DoesNotExist:
            return Response({'error': 'CourseCategory not found'}, status=status.HTTP_404_NOT_FOUND)