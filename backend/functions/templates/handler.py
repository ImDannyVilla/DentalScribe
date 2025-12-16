# functions/templates/handler.py
import json
import boto3
import os
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Key

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


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
    }


def lambda_handler(event, context):
    """Main handler that routes to appropriate function based on HTTP method"""
    
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': ''
        }
    
    http_method = event.get('httpMethod', 'GET')
    path_params = event.get('pathParameters') or {}
    template_id = path_params.get('template_id')
    
    try:
        # Get user info from Cognito claims
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_id = claims.get('sub', 'anonymous')
        user_role = claims.get('custom:role', 'user')
        
        if http_method == 'GET':
            if template_id:
                return get_template(template_id)
            else:
                return list_templates(user_id)
        
        elif http_method == 'POST':
            # Only admins can create templates
            if user_role != 'admin':
                return {
                    'statusCode': 403,
                    'headers': get_cors_headers(),
                    'body': json.dumps({'error': 'Only admins can create templates'})
                }
            return create_template(event, user_id)
        
        elif http_method == 'PUT':
            if user_role != 'admin':
                return {
                    'statusCode': 403,
                    'headers': get_cors_headers(),
                    'body': json.dumps({'error': 'Only admins can update templates'})
                }
            return update_template(event, template_id, user_id)
        
        elif http_method == 'DELETE':
            if user_role != 'admin':
                return {
                    'statusCode': 403,
                    'headers': get_cors_headers(),
                    'body': json.dumps({'error': 'Only admins can delete templates'})
                }
            return delete_template(template_id)
        
        else:
            return {
                'statusCode': 405,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Method not allowed'})
            }
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def list_templates(user_id):
    """List all templates (defaults + custom)"""
    try:
        # Get custom templates from DynamoDB
        response = table.scan()
        custom_templates = response.get('Items', [])
        
        # Combine with defaults
        all_templates = DEFAULT_TEMPLATES + custom_templates
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'templates': all_templates,
                'count': len(all_templates)
            })
        }
    except Exception as e:
        print(f"Error listing templates: {str(e)}")
        # Return defaults if DB fails
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'templates': DEFAULT_TEMPLATES,
                'count': len(DEFAULT_TEMPLATES)
            })
        }


def get_template(template_id):
    """Get a specific template by ID"""
    # Check defaults first
    for template in DEFAULT_TEMPLATES:
        if template['template_id'] == template_id:
            return {
                'statusCode': 200,
                'headers': get_cors_headers(),
                'body': json.dumps({'template': template})
            }
    
    # Check custom templates
    try:
        response = table.get_item(Key={'template_id': template_id})
        template = response.get('Item')
        
        if not template:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Template not found'})
            }
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({'template': template})
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def create_template(event, user_id):
    """Create a new custom template"""
    try:
        body = json.loads(event.get('body', '{}'))
        
        name = body.get('name', '').strip()
        description = body.get('description', '').strip()
        example_output = body.get('example_output', '').strip()
        
        if not name:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Template name is required'})
            }
        
        if not example_output:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Example output is required'})
            }
        
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
        
        return {
            'statusCode': 201,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'message': 'Template created successfully',
                'template': item
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def update_template(event, template_id, user_id):
    """Update an existing custom template"""
    # Cannot update default templates
    for template in DEFAULT_TEMPLATES:
        if template['template_id'] == template_id:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Cannot modify default templates'})
            }
    
    try:
        body = json.loads(event.get('body', '{}'))
        
        name = body.get('name', '').strip()
        description = body.get('description', '').strip()
        example_output = body.get('example_output', '').strip()
        
        if not name:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Template name is required'})
            }
        
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
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'message': 'Template updated successfully',
                'template': response.get('Attributes', {})
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }


def delete_template(template_id):
    """Delete a custom template"""
    # Cannot delete default templates
    for template in DEFAULT_TEMPLATES:
        if template['template_id'] == template_id:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Cannot delete default templates'})
            }
    
    try:
        table.delete_item(Key={'template_id': template_id})
        
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({'message': 'Template deleted successfully'})
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }
