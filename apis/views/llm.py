from django.db.models import Q, CharField, TextField, ForeignKey, ManyToManyField, Model
from django.core.exceptions import FieldDoesNotExist
from django.contrib.auth.models import User
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from ..models import (
    ActionItem, Project, Course, CourseCategory, EmployeeProfile, 
    ProjectAllocation, Survey, SurveyQuestion, SurveyResponse, SurveyAnswer
)
from ..permissions import IsManagerOrAssociate
from ..utils import get_table_schema
import json
import requests
from datetime import datetime

# All available models except User (as per requirement)
MODEL_MAPPING = {
    "actionitem": ActionItem,
    "project": Project,
    "course": Course,
    "coursecategory": CourseCategory,
    "employeeprofile": EmployeeProfile,
    "projectallocation": ProjectAllocation,
    "survey": Survey,
    "surveyquestion": SurveyQuestion,
    "surveyresponse": SurveyResponse,
    "surveyanswer": SurveyAnswer,
}

class ChatAPIView(APIView):
    """Enhanced LLM-powered chat API with comprehensive database querying and role-based access control"""
    permission_classes = [IsAuthenticated, IsManagerOrAssociate]

    def post(self, request, *args, **kwargs):
        user_prompt = request.data.get("prompt", "").strip()
        if not user_prompt:
            return HttpResponse(
                self.generate_error_html("Missing prompt. Please provide a query."),
                content_type='text/html'
            )

        user = request.user
        try:
            user_profile = user.employee_profile
        except EmployeeProfile.DoesNotExist:
            return HttpResponse(
                self.generate_error_html("Employee profile not found."),
                content_type='text/html'
            )

        # Compose enhanced LLM prompt with all available models
        schema_prompt = (
            "You are an intelligent corporate data assistant. You help employees query company data.\n"
            "Given a user query and database schemas, respond with a JSON object specifying which model to query and search filters.\n"
            "Available models and their purposes:\n"
            "- actionitem: Tasks and action items assigned to employees\n"
            "- project: Company projects and their details\n"
            "- course: Training courses and learning materials\n"
            "- coursecategory: Categories for organizing courses\n"
            "- employeeprofile: Employee information and profiles\n"
            "- projectallocation: Employee assignments to projects\n"
            "- survey: Employee surveys and feedback forms\n"
            "- surveyquestion: Individual questions within surveys\n"
            "- surveyresponse: Employee responses to surveys\n"
            "- surveyanswer: Specific answers to survey questions\n\n"
        )

        for name, model in MODEL_MAPPING.items():
            schema = get_table_schema(model, preferred_table_name=name)
            schema_prompt += f"\n{name.upper()} Schema:\n{schema}\n"

        schema_prompt += (
            f'\nUser Query: "{user_prompt}"\n\n'
            "Instructions:\n"
            "1. Analyze the user query and determine the most relevant model\n"
            "2. Extract key search terms that would help filter the data\n"
            "3. Respond ONLY with a JSON object in this exact format:\n"
            '{"model": "modelname", "filters": ["keyword1", "keyword2"], "intent": "brief description of what user wants"}\n'
            "4. If no suitable model matches, use null for the model\n"
            "5. Include 2-5 relevant keywords for filtering\n"
            "6. No additional text outside the JSON object\n"
        )

        # Make LLM call
        try:
            llm_result = self.call_llm(schema_prompt)
            if not llm_result:
                return HttpResponse(
                    self.generate_error_html("Failed to process your query. Please try again."),
                    content_type='text/html'
                )
        except Exception as e:
            return HttpResponse(
                self.generate_error_html(f"LLM processing error: {str(e)}"),
                content_type='text/html'
            )

        model_name = llm_result.get('model', '').lower().strip()
        keywords = llm_result.get('filters', [])
        intent = llm_result.get('intent', 'Data query')

        if not model_name or model_name == 'null':
            return HttpResponse(
                self.generate_error_html("I couldn't understand your query. Please try rephrasing it."),
                content_type='text/html'
            )

        model = MODEL_MAPPING.get(model_name)
        if not model:
            return HttpResponse(
                self.generate_error_html(f"Model '{model_name}' is not available for querying."),
                content_type='text/html'
            )

        # Apply role-based access control
        try:
            queryset = self.apply_role_based_filtering(model, user, user_profile, keywords)
        except PermissionError as e:
            return HttpResponse(
                self.generate_error_html(str(e)),
                content_type='text/html'
            )

        # Generate HTML response
        html_response = self.generate_data_html(
            queryset, model, keywords, intent, user_profile
        )
        
        return HttpResponse(html_response, content_type='text/html')

    def call_llm(self, prompt):
        """Make LLM API call and parse response"""
        payload = {
            "model": "codellama:13b",
            "prompt": prompt,
            "stream": False,
            "temperature": 0.1,
        }

        try:
            response = requests.post(
                "http://ec2-13-201-68-87.ap-south-1.compute.amazonaws.com:11434/api/generate",
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=None
            )
            response.raise_for_status()
            
            raw_output = response.json().get("response", "").strip()
            # Clean up the response to extract JSON
            if '{' in raw_output and '}' in raw_output:
                start = raw_output.find('{')
                end = raw_output.rfind('}') + 1
                json_str = raw_output[start:end]
                return json.loads(json_str)
            else:
                return None
                
        except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
            print(f"LLM call error: {e}")
            return None

    def apply_role_based_filtering(self, model, user, user_profile, keywords):
        """Apply role-based access control to database queries"""
        # Build base query from keywords
        query = Q()
        for kw in keywords:
            for field in model._meta.get_fields():
                field_name = field.name
                
                # Skip sensitive fields
                if field_name in ['password', 'is_superuser', 'is_staff']:
                    continue

                # Handle ForeignKey and ManyToMany relationships
                if isinstance(field, (ForeignKey, ManyToManyField)):
                    related_model = field.related_model
                    if related_model == User:  # Skip User model queries
                        continue
                        
                    candidate_fields = ['name', 'title', 'description', 'username', 'first_name', 'last_name']
                    for f in candidate_fields:
                        try:
                            related_model._meta.get_field(f)
                            query |= Q(**{f"{field_name}__{f}__icontains": kw})
                        except FieldDoesNotExist:
                            pass

                # Handle text fields
                elif isinstance(field, (CharField, TextField)):
                    query |= Q(**{f"{field_name}__icontains": kw})

        # Get base queryset
        queryset = model.objects.filter(query).distinct()

        # Apply role-based filtering
        if model == EmployeeProfile:
            if user_profile.is_manager:
                # Managers can query their team members
                team_user_ids = [emp.user.id for emp in EmployeeProfile.objects.filter(manager=user)]
                team_user_ids.append(user.id)  # Include manager themselves
                queryset = queryset.filter(user__id__in=team_user_ids)
            else:
                # Associates can only query themselves
                queryset = queryset.filter(user=user)
                
        elif hasattr(model, 'assigned_to'):
            # For models with assigned_to field (ActionItem, etc.)
            if user_profile.is_manager:
                # Managers can see items assigned to their team
                team_user_ids = [emp.user.id for emp in EmployeeProfile.objects.filter(manager=user)]
                team_user_ids.append(user.id)
                queryset = queryset.filter(assigned_to__id__in=team_user_ids)
            else:
                # Associates can only see their own items
                queryset = queryset.filter(assigned_to=user)
                
        elif hasattr(model, 'created_by'):
            # For models with created_by field (Survey, etc.)
            if user_profile.is_manager:
                # Managers can see items they created or items for their team
                team_user_ids = [emp.user.id for emp in EmployeeProfile.objects.filter(manager=user)]
                team_user_ids.append(user.id)
                queryset = queryset.filter(
                    Q(created_by=user) | Q(created_by__id__in=team_user_ids)
                )
            else:
                # Associates can see surveys created by their manager or public surveys
                manager_surveys = Q(created_by=user_profile.manager) if user_profile.manager else Q()
                public_surveys = Q(target_audience='all')
                queryset = queryset.filter(manager_surveys | public_surveys)

        # Limit results to prevent overwhelming responses
        return queryset[:50]

    def generate_data_html(self, queryset, model, keywords, intent, user_profile):
        """Generate HTML response with query results"""
        model_name = model.__name__
        count = queryset.count()
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Query Results - {model_name}</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ border-bottom: 2px solid #a5479f; padding-bottom: 20px; margin-bottom: 30px; }}
                .header h1 {{ color: #a5479f; margin: 0; font-size: 28px; }}
                .header p {{ color: #666; margin: 10px 0 0 0; font-size: 16px; }}
                .meta {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 25px; border-left: 4px solid #a5479f; }}
                .meta strong {{ color: #a5479f; }}
                .results {{ margin-top: 20px; }}
                .result-item {{ background: #fff; border: 1px solid #e1e5e9; border-radius: 8px; padding: 20px; margin-bottom: 15px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
                .result-item:hover {{ box-shadow: 0 4px 8px rgba(0,0,0,0.1); transition: box-shadow 0.2s; }}
                .result-title {{ font-size: 18px; font-weight: 600; color: #2c3e50; margin-bottom: 10px; }}
                .result-field {{ margin: 8px 0; padding: 5px 0; }}
                .field-label {{ font-weight: 600; color: #a5479f; display: inline-block; width: 120px; }}
                .field-value {{ color: #555; }}
                .no-results {{ text-align: center; padding: 40px; color: #666; font-size: 18px; }}
                .timestamp {{ text-align: right; color: #999; font-size: 12px; margin-top: 20px; }}
                .role-badge {{ background: #a5479f; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: 500; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔍 Query Results: {model_name}</h1>
                    <p>{intent}</p>
                </div>
                
                <div class="meta">
                    <p><strong>Query:</strong> {', '.join(keywords) if keywords else 'All records'}</p>
                    <p><strong>Model:</strong> {model_name} | <strong>Results:</strong> {count} records found</p>
                    <p><strong>User:</strong> {user_profile.user.get_full_name() or user_profile.user.username} 
                       <span class="role-badge">{'Manager' if user_profile.is_manager else 'Associate'}</span></p>
                </div>
        """

        if count == 0:
            html += """
                <div class="no-results">
                    <h3>No results found</h3>
                    <p>Try adjusting your search terms or check if you have access to this data.</p>
                </div>
            """
        else:
            html += '<div class="results">'
            
            for obj in queryset:
                html += self.format_object_html(obj, model)
                
            html += '</div>'

        html += f"""
                <div class="timestamp">
                    Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

    def format_object_html(self, obj, model):
        """Format individual object as HTML"""
        html = '<div class="result-item">'
        
        # Try to get a meaningful title
        title = 'Record'
        if hasattr(obj, 'title'):
            title = obj.title
        elif hasattr(obj, 'name'):
            title = obj.name
        elif hasattr(obj, 'question_text'):
            title = obj.question_text[:100] + '...' if len(obj.question_text) > 100 else obj.question_text
        elif hasattr(obj, 'user'):
            title = f"{obj.user.get_full_name() or obj.user.username}"
            
        html += f'<div class="result-title">{title}</div>'
        
        # Display relevant fields based on model type
        fields_to_show = self.get_relevant_fields(model)
        
        for field_name in fields_to_show:
            try:
                field = model._meta.get_field(field_name)
                value = getattr(obj, field_name, None)
                
                if value is not None:
                    # Format the value appropriately
                    if isinstance(field, (ForeignKey, ManyToManyField)):
                        if isinstance(field, ForeignKey):
                            display_value = str(value)
                        else:  # ManyToMany
                            display_value = ', '.join([str(v) for v in value.all()[:3]])
                            if value.count() > 3:
                                display_value += f' (+{value.count() - 3} more)'
                    elif hasattr(value, 'strftime'):  # DateTime field
                        display_value = value.strftime('%Y-%m-%d %H:%M')
                    else:
                        display_value = str(value)
                        
                    # Truncate long values
                    if len(display_value) > 200:
                        display_value = display_value[:200] + '...'
                        
                    html += f"""
                        <div class="result-field">
                            <span class="field-label">{field_name.replace('_', ' ').title()}:</span>
                            <span class="field-value">{display_value}</span>
                        </div>
                    """
            except (FieldDoesNotExist, AttributeError):
                continue
                
        html += '</div>'
        return html

    def get_relevant_fields(self, model):
        """Get relevant fields to display for each model type"""
        field_mapping = {
            ActionItem: ['assigned_to', 'title', 'status', 'action', 'created_at'],
            Project: ['title', 'description', 'status', 'criticality', 'start_date', 'go_live_date'],
            Course: ['title', 'description', 'source', 'created_at'],
            CourseCategory: ['name', 'description'],
            EmployeeProfile: ['user', 'role', 'mental_health', 'motivation_factor', 'manager'],
            ProjectAllocation: ['employee', 'project', 'allocation_percentage', 'start_date', 'end_date'],
            Survey: ['title', 'description', 'survey_type', 'status', 'created_by', 'start_date', 'end_date'],
            SurveyQuestion: ['survey', 'question_text', 'question_type', 'is_required'],
            SurveyResponse: ['survey', 'respondent', 'is_completed', 'submitted_at'],
            SurveyAnswer: ['response', 'question', 'answer_text', 'answer_rating', 'answer_boolean']
        }
        
        return field_mapping.get(model, ['id', 'created_at'])

    def generate_error_html(self, error_message):
        """Generate HTML error response"""
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Query Error</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 50px auto; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }}
                .error-icon {{ font-size: 48px; margin-bottom: 20px; }}
                .error-title {{ color: #e74c3c; font-size: 24px; margin-bottom: 15px; }}
                .error-message {{ color: #666; font-size: 16px; line-height: 1.5; }}
                .timestamp {{ color: #999; font-size: 12px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="error-icon">⚠️</div>
                <h2 class="error-title">Query Error</h2>
                <p class="error-message">{error_message}</p>
                <div class="timestamp">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
        </body>
        </html>
        """
