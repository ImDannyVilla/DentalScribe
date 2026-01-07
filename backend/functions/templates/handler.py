# functions/templates/handler.py
import json
import boto3
import os
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Key
from security import format_response, format_error, validate_input, require_admin, ValidationError

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TEMPLATES_TABLE', 'DentalScribeTemplates-prod'))

# Default templates that are always available
DEFAULT_TEMPLATES = [
    {
        'template_id': 'default_soap',
        'name': 'SOAP General',
        'description': 'Standard SOAP format for general dentistry visits',
        'is_default': True,
        'example_output': '''SUBJECTIVE:
Patient presents for [reason]. Reports [symptoms/concerns].

OBJECTIVE:
Exam findings: [clinical observations]
Teeth examined: [tooth numbers]
Radiographs: [if applicable]

ASSESSMENT:
[Diagnosis and clinical impression]

PLAN:
1. [Treatment performed]
2. [Follow-up recommendations]
3. [Next appointment]'''
    },
    {
        'template_id': 'default_hygiene',
        'name': 'Hygiene Recall',
        'description': 'Template for routine cleaning and hygiene visits',
        'is_default': True,
        'example_output': '''SUBJECTIVE:
Patient presents for routine prophylaxis. [Any concerns reported]

OBJECTIVE:
Probing depths: [findings]
Bleeding on probing: [yes/no, locations]
Plaque score: [percentage]
Calculus: [light/moderate/heavy]

ASSESSMENT:
[Periodontal status]

PLAN:
1. Prophylaxis completed
2. Fluoride treatment: [yes/no]
3. OHI provided
4. Return in [timeframe]'''
    },
    {
        'template_id': 'default_limited',
        'name': 'Limited Exam (Emergency)',
        'description': 'Template for emergency/limited examination visits',
        'is_default': True,
        'example_output': '''CHIEF COMPLAINT:
[Patient's primary concern in their words]

HISTORY OF PRESENT ILLNESS:
Onset: [when symptoms started]
Duration: [how long]
Character: [sharp/dull/throbbing]
Location: [specific tooth/area]
Aggravating factors: [hot/cold/biting]
Relieving factors: [what helps]

CLINICAL FINDINGS:
[Exam observations]

RADIOGRAPHIC FINDINGS:
[X-ray interpretation]

DIAGNOSIS:
[Clinical diagnosis]

TREATMENT PROVIDED:
[Procedures performed today]

RECOMMENDATIONS:
[Follow-up care needed]'''
    }
]


def lambda_handler(event, context):
    """Main handler that routes to appropriate function based on HTTP method"""
    
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {})
    
    http_method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters') or {}
    template_id = path_params.get('template_id')
    
    try:
        if http_method == 'GET':
            if template_id:
                return get_template(template_id)
            else:
                return list_templates()
        
        # POST/PUT/DELETE - admin only
        if http_method in ['POST', 'PUT', 'DELETE']:
            try:
                user_info = require_admin(event)
                user_id = user_info['user_id']
            except ValidationError as e:
                return format_error(403, e.message, method=http_method)
            
            if http_method == 'POST':
                return create_template(event, user_id)
            elif http_method == 'PUT':
                return update_template(event, template_id, user_id)
            elif http_method == 'DELETE':
                return delete_template(template_id)
        
        return format_error(405, f"Method {http_method} not allowed", method=http_method)
            
    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e)


def list_templates():
    """List all templates (defaults + custom)"""
    try:
        # Get custom templates from DynamoDB
        response = table.scan()
        custom_templates = response.get('Items', [])
        
        # Combine with defaults
        all_templates = DEFAULT_TEMPLATES + custom_templates
        
        return format_response(200, {
            'templates': all_templates,
            'count': len(all_templates)
        })
    except Exception as e:
        # Return defaults if DB fails
        return format_response(200, {
            'templates': DEFAULT_TEMPLATES,
            'count': len(DEFAULT_TEMPLATES)
        })


def get_template(template_id):
    """Get a specific template by ID"""
    # Check defaults first
    for template in DEFAULT_TEMPLATES:
        if template['template_id'] == template_id:
            return format_response(200, {'template': template})
    
    # Check custom templates
    try:
        response = table.get_item(Key={'template_id': template_id})
        template = response.get('Item')
        
        if not template:
            return format_error(404, "Template not found")
        
        return format_response(200, {'template': template})
    except Exception as e:
        return format_error(500, "Failed to get template", internal_error=e)


def create_template(event, user_id):
    """Create a new custom template"""
    try:
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return format_error(400, "Invalid JSON in request body", method='POST')
        
        is_valid, error_msg = validate_input(body, ['name', 'example_output'])
        if not is_valid:
            return format_error(400, error_msg, method='POST')

        name = body.get('name', '').strip()
        description = body.get('description', '').strip()
        example_output = body.get('example_output', '').strip()
        
        template_id = f"custom_{uuid.uuid4().hex[:8]}"
        timestamp = datetime.utcnow().isoformat()
        
        item = {
            'template_id': template_id,
            'name': name,
            'description': description,
            'example_output': example_output,
            'is_default': False,
            'created_by': user_id,
            'created_at': timestamp,
            'updated_at': timestamp
        }
        
        table.put_item(Item=item)
        
        return format_response(201, {
            'message': 'Template created successfully',
            'template': item
        }, method='POST')
        
    except Exception as e:
        return format_error(500, "Failed to create template", internal_error=e, method='POST')


def update_template(event, template_id, user_id):
    """Update an existing custom template"""
    # Cannot update default templates
    for template in DEFAULT_TEMPLATES:
        if template['template_id'] == template_id:
            return format_error(400, "Cannot modify default templates", method='PUT')
    
    try:
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return format_error(400, "Invalid JSON in request body", method='PUT')
        
        name = body.get('name', '').strip()
        description = body.get('description', '').strip()
        example_output = body.get('example_output', '').strip()
        
        if not name:
            return format_error(400, "Template name is required", method='PUT')
        
        timestamp = datetime.utcnow().isoformat()
        
        response = table.update_item(
            Key={'template_id': template_id},
            UpdateExpression='SET #name = :name, description = :desc, example_output = :example, updated_at = :updated, updated_by = :user',
            ExpressionAttributeNames={'#name': 'name'},
            ExpressionAttributeValues={
                ':name': name,
                ':desc': description,
                ':example': example_output,
                ':updated': timestamp,
                ':user': user_id
            },
            ReturnValues='ALL_NEW'
        )
        
        return format_response(200, {
            'message': 'Template updated successfully',
            'template': response.get('Attributes', {})
        }, method='PUT')
        
    except Exception as e:
        return format_error(500, "Failed to update template", internal_error=e, method='PUT')


def delete_template(template_id):
    """Delete a custom template"""
    # Cannot delete default templates
    for template in DEFAULT_TEMPLATES:
        if template['template_id'] == template_id:
            return format_error(400, "Cannot delete default templates", method='DELETE')
    
    try:
        table.delete_item(Key={'template_id': template_id})
        
        return format_response(200, {'message': 'Template deleted successfully'}, method='DELETE')
        
    except Exception as e:
        return format_error(500, "Failed to delete template", internal_error=e, method='DELETE')
