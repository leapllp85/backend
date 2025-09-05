import uuid
import threading
import json
import time
from datetime import datetime, timedelta
from django.http import JsonResponse
from django.core.cache import cache
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from apis.permissions import IsManager
from apis.models import EmployeeProfile, Project, Course, Survey, ActionItem, ProjectAllocation, Conversation, ConversationMessage
from anthropic import Anthropic
from django.db import connection
import logging

logger = logging.getLogger(__name__)


class ChatInitiateView(APIView):
    """Initiate a chat conversation and start background processing with caching support"""
    permission_classes = [IsAuthenticated, IsManager]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Import cache methods from sync chat API
        from .llm import ChatAPIView
        self.chat_api = ChatAPIView()

    def post(self, request, *args, **kwargs):
        try:
            # Accept both 'query' and 'prompt' parameters for compatibility
            user_query = request.data.get('query', '').strip() or request.data.get('prompt', '').strip()
            conversation_id = request.data.get('conversation_id')
            
            if not user_query:
                return Response({
                    "error": "Query is required",
                    "success": False
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check cache for similar queries first
            user_profile = request.user.employee_profile
            cached_response = self.chat_api.get_cached_response(request.user.username, user_query, user_profile)
            
            if cached_response:
                logger.info(f"Async cache hit for user {request.user.username}, query: {user_query[:50]}...")
                
                # Create conversation and messages for tracking
                conversation = self._get_or_create_conversation(request.user, conversation_id, user_query)
                user_message = ConversationMessage.objects.create(
                    conversation=conversation,
                    role='user',
                    content=user_query
                )
                assistant_message = ConversationMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=f"Generated analysis for: {user_query} (cached)",
                    analysis_data=cached_response.get('analysis'),
                    queries_data=cached_response.get('queries'),
                    dataset=cached_response.get('dataset')
                )
                
                # Return cached response immediately with conversation metadata
                cached_response.update({
                    "conversation_id": str(conversation.id),
                    "message_id": str(assistant_message.id),
                    "cached": True,
                    "task_id": "cached",
                    "status": "completed"
                })
                
                return Response(cached_response, status=status.HTTP_200_OK)

            # Generate unique task ID for non-cached requests
            task_id = str(uuid.uuid4())
            
            # Initialize task status in Redis with optimized structure
            task_key = f"chat_task:{task_id}"
            try:
                cache.set(task_key, {
                    "status": "processing",
                    "created_at": datetime.now().isoformat(),
                    "user_id": request.user.id,
                    "query": user_query[:200],  # Limit query length in cache
                    "conversation_id": conversation_id,
                    "progress": "Initializing...",
                    "task_id": task_id
                }, timeout=settings.CHAT_PROCESSING_TIMEOUT)
            except Exception as e:
                logger.error(f"Error setting task status: {e}")
                return Response({
                    "error": "Failed to set task status",
                    "success": False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Start background processing
            thread = threading.Thread(
                target=self._process_chat_in_background,
                args=(task_id, request.user.id, user_query, conversation_id)
            )
            thread.daemon = True
            thread.start()

            return Response({
                "task_id": task_id,
                "status": "processing",
                "message": "Chat processing initiated. Use the task_id to check status and retrieve response.",
                "success": True
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.error(f"Error initiating chat: {e}")
            return Response({
                "error": "Failed to initiate chat processing",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _process_chat_in_background(self, task_id, user_id, user_query, conversation_id):
        """Background processing of chat request with caching support"""
        task_key = f"chat_task:{task_id}"
        
        try:
            # Update status
            self._update_task_status(task_key, "processing", "Loading user profile...")
            
            # Get user and profile
            from django.contrib.auth.models import User
            user = User.objects.get(id=user_id)
            user_profile = user.employee_profile
            
            # Initialize chat API for caching methods
            from .llm import ChatAPIView
            self.chat_api = ChatAPIView()
            
            # Update status
            self._update_task_status(task_key, "processing", "Managing conversation...")
            
            # Handle conversation management
            conversation = self._get_or_create_conversation(user, conversation_id, user_query)
            
            # Save user message
            ConversationMessage.objects.create(
                conversation=conversation,
                role='user',
                content=user_query
            )
            
            # Update status
            self._update_task_status(task_key, "processing", "Gathering context data...")
            
            # Get context data (with caching)
            context_data = self.chat_api.get_cached_database_context(user, user_profile, user_query)
            
            if not context_data:
                error_message = "No relevant information found for your query. Try rephrasing or asking about projects, employees, courses, or surveys."
                
                # Save error as assistant message
                ConversationMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=error_message
                )
                
                # Update task with error using optimized structure
                cache.set(task_key, {
                    "status": "completed",
                    "success": False,
                    "error": error_message,
                    "conversation_id": str(conversation.id),
                    "completed_at": datetime.now().isoformat(),
                    "task_id": task_id,
                    "user_id": user_id
                }, timeout=settings.CHAT_RESPONSE_TTL)
                return
            
            # Update status
            self._update_task_status(task_key, "processing", "Generating AI response...")
            
            # Generate structured data response using Claude
            response_data = self._generate_claude_data_response(
                user_query=user_query,
                context_data=context_data,
                user_profile=user_profile
            )
            
            # Check if response_data is valid before proceeding
            if not isinstance(response_data, dict) or not response_data.get("success", True):
                error_message = response_data.get("error", "Failed to generate AI response") if isinstance(response_data, dict) else str(response_data)
                
                # Save error as assistant message
                ConversationMessage.objects.create(
                    conversation=conversation,
                    role='assistant',
                    content=error_message
                )
                
                # Update task with error
                cache.set(task_key, {
                    "status": "failed",
                    "success": False,
                    "error": error_message,
                    "conversation_id": str(conversation.id),
                    "completed_at": datetime.now().isoformat(),
                    "task_id": task_id,
                    "user_id": user_id
                }, timeout=settings.CHAT_RESPONSE_TTL)
                return
            
            # Save assistant response
            assistant_message = ConversationMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=f"Generated analysis for: {user_query}",
                analysis_data=response_data.get('analysis'),
                queries_data=response_data.get('queries'),
                dataset=response_data.get('dataset')
            )
            
            # Create optimized response matching the sync API format
            # Map dataset by component IDs and filter out empty components
            dataset_by_component, valid_components = self._map_dataset_to_components(
                response_data.get('components', []), 
                response_data.get('dataset', [])
            )
            
            # Update layout to only include valid components
            layout = response_data.get('layout', {})
            if 'component_arrangement' in layout and valid_components:
                valid_component_ids = {comp.get('id') for comp in valid_components}
                layout['component_arrangement'] = [
                    arrangement for arrangement in layout['component_arrangement']
                    if arrangement.get('component_id') in valid_component_ids
                ]
            
            optimized_response = {
                "success": True,
                "conversation_id": str(conversation.id),
                "message_id": str(assistant_message.id),
                "layout": layout,
                "components": valid_components,
                "dataset": dataset_by_component,
                "insights": response_data.get('insights', {}),
                "cached": False
            }
            
            # Cache the successful response using the sync API's caching method (only if meaningful data)
            self.chat_api.cache_response(user.username, user_query, optimized_response, user_profile)
            
            # Store final response in Redis with optimized structure
            final_response = {
                "status": "completed",
                "task_id": task_id,
                "user_id": user_id,
                "completed_at": datetime.now().isoformat(),
                **optimized_response  # Merge optimized response fields
            }
            
            cache.set(task_key, final_response, timeout=settings.CHAT_RESPONSE_TTL)
            
        except Exception as e:
            logger.error(f"Error processing chat task {task_id}: {e}")
            # Store error in Redis with optimized structure
            cache.set(task_key, {
                "status": "failed",
                "success": False,
                "error": str(e)[:500],  # Limit error message length
                "completed_at": datetime.now().isoformat(),
                "task_id": task_id,
                "user_id": user_id
            }, timeout=settings.CHAT_RESPONSE_TTL)

    def _update_task_status(self, task_key, status, progress):
        """Update task status in Redis"""
        try:
            current_data = cache.get(task_key, {})
            current_data.update({
                "status": status,
                "progress": progress,
                "updated_at": datetime.now().isoformat()
            })
            cache.set(task_key, current_data, timeout=settings.CHAT_PROCESSING_TIMEOUT)
        except Exception as e:
            logger.error(f"Error updating task status: {e}")
    
    def _map_dataset_to_components(self, components, dataset):
        """Map dataset to components by component IDs with proper data processing"""
        dataset_by_component = {}
        valid_components = []
        
        if not isinstance(dataset, list) or not dataset:
            logger.error(f"Dataset is not a list: {type(dataset)}")
            return {}, []
        
        base_data = dataset[0].get('data', [])
        base_columns = dataset[0].get('columns', [])
        
        for component in components:
            # Ensure component is a dictionary
            if not isinstance(component, dict):
                logger.error(f"Component is not a dictionary: {type(component)}")
                continue
                
            component_id = component.get('id', f'component_{len(dataset_by_component) + 1}')
            component_type = component.get('type', '')
            
            # Process data based on component type
            processed_data = self._process_component_data(component, base_data, base_columns)
            
            # Check if component has meaningful data
            if self._has_meaningful_data(processed_data, component_type):
                # Get appropriate columns for this component type
                component_columns = self._get_component_columns(component_type, processed_data, base_columns)
                
                # Store processed data for this component
                dataset_by_component[component_id] = {
                    'data': processed_data,
                    'columns': component_columns,
                    'row_count': len(processed_data),
                    'description': dataset[0].get('description', f'Data for {component_type}')
                }
                
                # Add to valid components list
                valid_components.append(component)
        
        return dataset_by_component, valid_components
    
    def _has_meaningful_data(self, processed_data, component_type):
        """Check if processed data contains meaningful information for the component"""
        if not processed_data or not isinstance(processed_data, list):
            return False
        
        # For metric cards, check if there are actual metrics with values > 0
        if component_type == 'metric_card':
            for item in processed_data:
                if isinstance(item, dict) and item.get('value', 0) > 0:
                    return True
            return False
        
        # For pie charts, check if there are categories with counts > 0
        elif component_type == 'pie_chart':
            for item in processed_data:
                if isinstance(item, dict) and item.get('value', 0) > 0:
                    return True
            return False
        
        # For bar/line charts, check if there are non-zero values
        elif component_type in ['bar_chart', 'line_chart']:
            for item in processed_data:
                if isinstance(item, dict) and item.get('y', 0) != 0:
                    return True
            return False
        
        # For data tables, check if there's actual data
        elif component_type == 'data_table':
            return len(processed_data) > 0
        
        # Default: has data if list is not empty
        return len(processed_data) > 0
    
    def _get_component_columns(self, component_type, processed_data, base_columns):
        """Get appropriate column names for component type based on processed data"""
        if not processed_data:
            return base_columns
            
        # For chart components, use the keys from processed data
        if component_type in ['pie_chart', 'bar_chart', 'line_chart']:
            if processed_data and isinstance(processed_data[0], dict):
                return list(processed_data[0].keys())
        
        # For metric cards, use metric-specific columns
        elif component_type == 'metric_card':
            if processed_data and isinstance(processed_data[0], dict):
                return ['label', 'value']
        
        # For tables and other components, use original columns plus any added display fields
        elif component_type == 'data_table':
            if processed_data and isinstance(processed_data[0], dict):
                # Get all unique keys from the processed data
                all_keys = set()
                for item in processed_data:
                    if isinstance(item, dict):
                        all_keys.update(item.keys())
                return list(all_keys)
        
        # Default to base columns
        return base_columns
    
    def _process_component_data(self, component, data, columns):
        """Process data based on component type and properties"""
        # Ensure component is a dictionary
        if not isinstance(component, dict):
            logger.error(f"Component is not a dictionary in _process_component_data: {type(component)}")
            return data
            
        component_type = component.get('type', '')
        properties = component.get('properties', {})
        
        # For pie_chart, we need aggregated data
        if component_type == 'pie_chart':
            data_field = properties.get('data_field', 'mental_health')
            if data_field in columns:
                # Aggregate data by the specified field
                aggregated = {}
                for row in data:
                    # Handle both dict and string data types
                    if isinstance(row, dict):
                        value = row.get(data_field, 'Unknown')
                    else:
                        # If row is not a dict, skip or handle appropriately
                        continue
                    aggregated[value] = aggregated.get(value, 0) + 1
                
                # Convert to format expected by pie chart
                return [{'label': k, 'value': v, data_field: k} for k, v in aggregated.items()]
        
        # For metric_card, calculate metrics
        elif component_type == 'metric_card':
            metrics = properties.get('metrics', [])
            
            # Handle case where metrics is a list of strings instead of dicts
            if metrics and isinstance(metrics[0], str):
                # Use generic metric transformation for string-based metrics
                return self._transform_metric_data(data)
            
            metric_data = []
            
            for metric in metrics:
                # Ensure metric is a dictionary
                if not isinstance(metric, dict):
                    continue
                    
                field = metric.get('field', 'mental_health')
                filter_condition = metric.get('filter', '')
                aggregation = metric.get('aggregation', 'count')
                
                if aggregation == 'count':
                    if filter_condition:
                        # Parse filter condition like "mental_health='High'" or "primary_trigger='MH'"
                        if '=' in filter_condition:
                            filter_field, filter_value = filter_condition.split('=', 1)
                            filter_field = filter_field.strip()
                            filter_value = filter_value.strip().strip('"\'')
                            count = sum(1 for row in data if isinstance(row, dict) and row.get(filter_field) == filter_value)
                        else:
                            count = len(data)
                    else:
                        count = len(data)
                    metric_data.append({
                        'label': metric.get('label', 'Metric'),
                        'value': count,
                        'field': field
                    })
                elif aggregation == 'avg':
                    # For risk score calculation
                    risk_values = {'High': 3, 'Medium': 2, 'Low': 1}
                    total_score = sum(risk_values.get(row.get(field, 'Low'), 1) for row in data if isinstance(row, dict))
                    valid_rows = sum(1 for row in data if isinstance(row, dict))
                    avg_score = total_score / valid_rows if valid_rows > 0 else 0
                    metric_data.append({
                        'label': metric.get('label', 'Average'),
                        'value': round(avg_score, 2),
                        'field': field
                    })
            
            # If no valid metrics were processed, fall back to generic transformation
            if not metric_data:
                return self._transform_metric_data(data)
                
            return metric_data
        
        # For data_table and insights_panel, return original data with all fields preserved
        return data
    
    def _transform_data_for_frontend(self, data, component_type):
        """Transform data to match frontend component expectations"""
        if not data or not isinstance(data, list):
            return data
        
        # Apply component-specific transformations
        if component_type == 'pie_chart':
            return self._transform_pie_chart_data(data)
        elif component_type == 'bar_chart':
            return self._transform_bar_chart_data(data)
        elif component_type == 'line_chart':
            return self._transform_line_chart_data(data)
        elif component_type == 'data_table':
            return self._transform_table_data(data)
        elif component_type == 'metric_card':
            return self._transform_metric_data(data)
        else:
            return self._transform_general_data(data)
    
    def _transform_general_data(self, data):
        """Generic data transformations for any dataset type"""
        transformed_data = []
        
        for item in data:
            if not isinstance(item, dict):
                transformed_data.append(item)
                continue
            
            # Start with original data
            transformed_item = item.copy()
            
            # Generic name field - works for any entity
            name = self._get_display_name(item)
            if name:
                transformed_item['name'] = name
            
            # Generic status/category mappings
            self._add_status_mappings(transformed_item, item)
            
            # Date formatting for any date fields
            self._format_date_fields(transformed_item, item)
            
            # Boolean field formatting
            self._format_boolean_fields(transformed_item, item)
            
            transformed_data.append(transformed_item)
        
        return transformed_data
    
    def _get_display_name(self, item):
        """Get display name for any entity type"""
        # Employee names
        if 'first_name' in item and 'last_name' in item:
            return f"{item['first_name']} {item['last_name']}"
        elif 'username' in item:
            return item['username']
        
        # Project names
        elif 'project_name' in item:
            return item['project_name']
        elif 'name' in item:
            return item['name']
        
        # Course names
        elif 'course_name' in item:
            return item['course_name']
        elif 'title' in item:
            return item['title']
        
        # Survey names
        elif 'survey_name' in item:
            return item['survey_name']
        elif 'survey_title' in item:
            return item['survey_title']
        
        # Generic fallbacks
        elif 'description' in item:
            return item['description'][:50] + '...' if len(str(item['description'])) > 50 else item['description']
        
        return None
    
    def _add_status_mappings(self, transformed_item, item):
        """Add generic status/category mappings"""
        # Employee-specific mappings
        if 'primary_trigger' in item:
            trigger_map = {
                'MH': 'Mental Health',
                'MT': 'Motivation Factor', 
                'CO': 'Career Opportunities',
                'PR': 'Personal Reason'
            }
            transformed_item['trigger_display'] = trigger_map.get(item['primary_trigger'], item['primary_trigger'])
        
        # Project status mappings
        if 'project_status' in item:
            status_map = {
                'ACTIVE': 'Active',
                'COMPLETED': 'Completed',
                'ON_HOLD': 'On Hold',
                'CANCELLED': 'Cancelled'
            }
            transformed_item['status_display'] = status_map.get(item['project_status'], item['project_status'])
        
        # Course status mappings
        if 'course_status' in item:
            transformed_item['status_display'] = item['course_status'].title() if isinstance(item['course_status'], str) else item['course_status']
        
        # Generic status field
        if 'status' in item and 'status_display' not in transformed_item:
            transformed_item['status_display'] = item['status'].title() if isinstance(item['status'], str) else item['status']
    
    def _format_date_fields(self, transformed_item, item):
        """Format date fields generically"""
        # Common date field names across all entity types
        date_fields = [
            'created_at', 'updated_at', 'start_date', 'end_date', 'go_live_date',
            'completion_date', 'due_date', 'launch_date', 'survey_date'
        ]
        
        for field in date_fields:
            if field in item and item[field]:
                date_value = item[field]
                if hasattr(date_value, 'strftime'):
                    transformed_item[f'{field}_display'] = date_value.strftime('%b %d, %Y')
                elif isinstance(date_value, str):
                    transformed_item[f'{field}_display'] = date_value
    
    def _format_boolean_fields(self, transformed_item, item):
        """Format boolean fields generically"""
        # Common boolean fields across entity types
        boolean_fields = [
            'is_active', 'is_manager', 'is_completed', 'is_published',
            'is_mandatory', 'is_approved', 'is_archived'
        ]
        
        for field in boolean_fields:
            if field in item:
                transformed_item[f'{field}_display'] = 'Yes' if item[field] else 'No'
    
    def _transform_pie_chart_data(self, data):
        """Transform data for pie charts - works with any dataset"""
        aggregated = {}
        
        for item in data:
            # Get categorical value from various possible fields
            category_value = self._get_category_value(item)
            aggregated[category_value] = aggregated.get(category_value, 0) + 1
        
        # Return pie chart format with consistent field names
        return [{
            'label': label,
            'value': count,
            'category': label,
            'count': count
        } for label, count in aggregated.items()]
    
    def _get_category_value(self, item):
        """Get categorical value for grouping from any dataset"""
        # Employee risk categories
        if 'manager_assessment_risk' in item:
            return item['manager_assessment_risk']
        elif 'mental_health' in item:
            return item['mental_health']
        
        # Project categories
        elif 'project_status' in item:
            return item['project_status']
        elif 'priority' in item:
            return item['priority']
        
        # Course categories
        elif 'course_category' in item:
            return item['course_category']
        elif 'difficulty_level' in item:
            return item['difficulty_level']
        
        # Survey categories
        elif 'survey_type' in item:
            return item['survey_type']
        elif 'response_status' in item:
            return item['response_status']
        
        # Generic status/category fields
        elif 'status' in item:
            return item['status']
        elif 'category' in item:
            return item['category']
        elif 'type' in item:
            return item['type']
        
        return 'Unknown'
    
    def _transform_bar_chart_data(self, data):
        """Transform data for bar charts - works with any dataset"""
        bar_data = []
        
        for item in data:
            # Get name/label for x-axis
            name = self._get_display_name(item) or f"Item {item.get('id', '')}"
            
            # Get numeric value for y-axis
            value = self._get_numeric_value(item)
            
            bar_data.append({
                'x': name,
                'y': value,
                'name': name,
                'value': value,
                'category': name
            })
        
        return bar_data
    
    def _get_numeric_value(self, item):
        """Get numeric value for charts from any dataset"""
        # Employee metrics
        if 'performance_score' in item:
            return item['performance_score']
        elif 'project_count' in item:
            return item['project_count']
        
        # Project metrics
        elif 'budget' in item:
            return item['budget']
        elif 'duration_days' in item:
            return item['duration_days']
        elif 'team_size' in item:
            return item['team_size']
        
        # Course metrics
        elif 'duration_hours' in item:
            return item['duration_hours']
        elif 'enrollment_count' in item:
            return item['enrollment_count']
        elif 'completion_rate' in item:
            return item['completion_rate']
        
        # Survey metrics
        elif 'response_count' in item:
            return item['response_count']
        elif 'rating' in item:
            return item['rating']
        elif 'score' in item:
            return item['score']
        
        # Generic numeric fields
        elif 'count' in item:
            return item['count']
        elif 'value' in item:
            return item['value']
        elif 'amount' in item:
            return item['amount']
        
        return 0
    
    def _transform_line_chart_data(self, data):
        """Transform data for line charts - works with any dataset"""
        line_data = []
        
        for i, item in enumerate(data):
            # Get numeric value for y-axis
            value = self._get_numeric_value(item)
            
            # Try to get a time-based x value, otherwise use sequence
            x_value = self._get_time_value(item, i)
            
            line_data.append({
                'x': x_value,
                'y': value,
                'time': x_value,
                'value': value,
                'point': i + 1
            })
        
        return line_data
    
    def _get_time_value(self, item, index):
        """Get time-based value for x-axis or fallback to index"""
        # Try date fields first
        date_fields = ['created_at', 'start_date', 'completion_date', 'survey_date']
        for field in date_fields:
            if field in item and item[field]:
                if hasattr(item[field], 'strftime'):
                    return item[field].strftime('%Y-%m-%d')
                return str(item[field])
        
        # Try numeric sequence fields
        if 'week' in item:
            return item['week']
        elif 'month' in item:
            return item['month']
        elif 'quarter' in item:
            return item['quarter']
        
        # Fallback to sequential index
        return index + 1
    
    def _transform_table_data(self, data):
        """Transform data for tables - works with any dataset"""
        transformed_data = []
        
        for item in data:
            transformed_item = item.copy()
            
            # Add display name column
            name = self._get_display_name(item)
            if name:
                # Use appropriate column name based on data type
                if 'first_name' in item or 'username' in item:
                    transformed_item['Employee Name'] = name
                elif 'project_name' in item:
                    transformed_item['Project Name'] = name
                elif 'course_name' in item or 'title' in item:
                    transformed_item['Course Name'] = name
                elif 'survey_name' in item:
                    transformed_item['Survey Name'] = name
                else:
                    transformed_item['Name'] = name
            
            # Add calculated fields based on available data
            self._add_calculated_fields(transformed_item, item)
            
            transformed_data.append(transformed_item)
        
        return transformed_data
    
    def _add_calculated_fields(self, transformed_item, item):
        """Add calculated fields based on available data"""
        # Employee risk score
        if 'mental_health' in item and 'motivation_factor' in item:
            risk_scores = {'High': 3, 'Medium': 2, 'Low': 1}
            mental_score = risk_scores.get(item['mental_health'], 1)
            motivation_score = risk_scores.get(item['motivation_factor'], 1)
            transformed_item['Risk Score'] = round((mental_score + motivation_score) / 2, 1)
        
        # Project completion percentage
        if 'completed_tasks' in item and 'total_tasks' in item and item['total_tasks'] > 0:
            completion = (item['completed_tasks'] / item['total_tasks']) * 100
            transformed_item['Completion %'] = round(completion, 1)
        
        # Course progress
        if 'completed_modules' in item and 'total_modules' in item and item['total_modules'] > 0:
            progress = (item['completed_modules'] / item['total_modules']) * 100
            transformed_item['Progress %'] = round(progress, 1)
        
        # Survey response rate
        if 'responses_received' in item and 'total_invites' in item and item['total_invites'] > 0:
            response_rate = (item['responses_received'] / item['total_invites']) * 100
            transformed_item['Response Rate %'] = round(response_rate, 1)
    
    def _transform_metric_data(self, data):
        """Transform data for metric cards - works with any dataset"""
        if not data:
            return []
        
        metrics = []
        
        # Total count with appropriate label
        total_label = self._get_total_label(data)
        metrics.append({
            'label': total_label,
            'value': len(data)
        })
        
        # Add dataset-specific metrics
        self._add_dataset_metrics(metrics, data)
        
        return metrics
    
    def _get_total_label(self, data):
        """Get appropriate total count label based on dataset"""
        if not data:
            return 'Total Items'
        
        sample_item = data[0]
        
        # Determine dataset type from fields
        if 'first_name' in sample_item or 'username' in sample_item:
            return 'Total Employees'
        elif 'project_name' in sample_item or 'project_status' in sample_item:
            return 'Total Projects'
        elif 'course_name' in sample_item or 'course_category' in sample_item:
            return 'Total Courses'
        elif 'survey_name' in sample_item or 'survey_type' in sample_item:
            return 'Total Surveys'
        else:
            return 'Total Items'
    
    def _add_dataset_metrics(self, metrics, data):
        """Add metrics specific to the dataset type"""
        sample_item = data[0] if data else {}
        
        # Employee metrics
        if 'performance_score' in sample_item:
            performance_scores = [item.get('performance_score', 0) for item in data if item.get('performance_score')]
            if performance_scores:
                avg_performance = sum(performance_scores) / len(performance_scores)
                metrics.append({
                    'label': 'Avg Performance',
                    'value': round(avg_performance, 1)
                })
        
        if 'manager_assessment_risk' in sample_item or 'mental_health' in sample_item:
            high_risk_count = sum(1 for item in data 
                                 if item.get('manager_assessment_risk') == 'High' or 
                                    item.get('mental_health') == 'High')
            if high_risk_count > 0:
                metrics.append({
                    'label': 'High Risk Count',
                    'value': high_risk_count
                })
        
        # Project metrics
        if 'budget' in sample_item:
            budgets = [item.get('budget', 0) for item in data if item.get('budget')]
            if budgets:
                total_budget = sum(budgets)
                metrics.append({
                    'label': 'Total Budget',
                    'value': f"${total_budget:,.0f}"
                })
        
        if 'project_status' in sample_item:
            active_count = sum(1 for item in data if item.get('project_status') == 'ACTIVE')
            metrics.append({
                'label': 'Active Projects',
                'value': active_count
            })
        
        # Course metrics
        if 'enrollment_count' in sample_item:
            enrollments = [item.get('enrollment_count', 0) for item in data if item.get('enrollment_count')]
            if enrollments:
                total_enrollments = sum(enrollments)
                metrics.append({
                    'label': 'Total Enrollments',
                    'value': total_enrollments
                })
        
        if 'completion_rate' in sample_item:
            completion_rates = [item.get('completion_rate', 0) for item in data if item.get('completion_rate')]
            if completion_rates:
                avg_completion = sum(completion_rates) / len(completion_rates)
                metrics.append({
                    'label': 'Avg Completion Rate',
                    'value': f"{round(avg_completion, 1)}%"
                })
        
        # Survey metrics
        if 'response_count' in sample_item:
            responses = [item.get('response_count', 0) for item in data if item.get('response_count')]
            if responses:
                total_responses = sum(responses)
                metrics.append({
                    'label': 'Total Responses',
                    'value': total_responses
                })
        
        if 'rating' in sample_item:
            ratings = [item.get('rating', 0) for item in data if item.get('rating')]
            if ratings:
                avg_rating = sum(ratings) / len(ratings)
                metrics.append({
                    'label': 'Avg Rating',
                    'value': round(avg_rating, 1)
                })

    def _get_or_create_conversation(self, user, conversation_id, user_query):
        """Get existing conversation or create new one"""
        if conversation_id:
            try:
                conversation = Conversation.objects.get(id=conversation_id, user=user)
                return conversation
            except Conversation.DoesNotExist:
                pass
        
        # Create new conversation
        title = user_query[:50] + "..." if len(user_query) > 50 else user_query
        conversation = Conversation.objects.create(
            user=user,
            title=title
        )
        return conversation

    def _get_database_context(self, user, user_profile, user_query):
        """Get relevant context data from database"""
        # Import the existing method from the original ChatAPIView
        from .llm import ChatAPIView
        chat_view = ChatAPIView()
        return chat_view.get_database_context(user, user_profile, user_query)

    def _generate_claude_data_response(self, user_query, context_data, user_profile):
        """Generate Claude response with optimization"""
        # Import the existing method from the original ChatAPIView
        from .llm import ChatAPIView
        chat_view = ChatAPIView()
        
        # Get raw response
        response_data = chat_view.generate_claude_data_response(user_query, context_data, user_profile)
        print(response_data)
        
        # Check if response_data is a dictionary (successful response) or string (error)
        if not isinstance(response_data, dict):
            # If it's not a dictionary, return error response
            return {
                "success": False,
                "error": f"Invalid response format: {str(response_data)}"
            }
        
        # Check if the response indicates an error
        if not response_data.get("success", True):
            return response_data
        
        # Apply optimizations for async processing
        if "queries" in response_data:
            dataset = chat_view.execute_queries(response_data["queries"])
            response_data["dataset"] = chat_view.optimize_dataset(dataset)
            
        # Process multicomponent data if components are specified
        if "components" in response_data:
            response_data = chat_view.process_multicomponent_data(response_data)
            
        # Apply cleanup for reduced response size
        response_data = chat_view.cleanup_response(response_data)
        
        return response_data


class ChatResponseView(APIView):
    """Retrieve chat response using task ID"""
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request, task_id, *args, **kwargs):
        try:
            task_key = f"chat_task:{task_id}"
            task_data = cache.get(task_key)
            
            if not task_data:
                return Response({
                    "error": "Task not found or expired",
                    "success": False
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if user owns this task
            if task_data.get('user_id') != request.user.id:
                return Response({
                    "error": "Access denied",
                    "success": False
                }, status=status.HTTP_403_FORBIDDEN)
            
            return Response(task_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving chat response: {e}")
            return Response({
                "error": "Failed to retrieve chat response",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ChatStatusView(APIView):
    """Get status of all user's chat tasks"""
    permission_classes = [IsAuthenticated, IsManager]

    def get(self, request, *args, **kwargs):
        try:
            # This is a simplified implementation
            # In production, you might want to store task IDs in a user-specific key
            return Response({
                "message": "Use specific task_id to check individual task status",
                "endpoint": "/api/chat/response/{task_id}/",
                "success": True
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error getting chat status: {e}")
            return Response({
                "error": "Failed to get chat status",
                "success": False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
