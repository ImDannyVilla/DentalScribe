# functions/patients/create.py
import json
import boto3
import os
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('PATIENTS_TABLE', 'DentalScribePatients-prod'))


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': ''
        }

    try:
        # Get user info from Cognito
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_id = claims.get('sub', 'unknown')

        # Use 'default' as practice_id for simplicity
        # Change this if you want multi-tenant support
        practice_id = 'default'

        # Parse request body
        body = json.loads(event.get('body', '{}'))

        name = body.get('name', '').strip()
        email = body.get('email', '').strip()
        phone = body.get('phone', '').strip()
        date_of_birth = body.get('date_of_birth', '').strip()

        if not name:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Patient name is required'})
            }

        # Generate patient ID
        patient_id = f"pat_{uuid.uuid4().hex[:12]}"
        timestamp = datetime.utcnow().isoformat()

        # Create patient record
        item = {
            'practice_id': practice_id,
            'patient_id': patient_id,
            'name': name,
            'name_lowercase': name.lower(),
            'created_by': user_id,
            'created_at': timestamp,
            'updated_at': timestamp
        }

        # Add optional fields if provided
        if email:
            item['email'] = email
        if phone:
            item['phone'] = phone
        if date_of_birth:
            item['date_of_birth'] = date_of_birth

        table.put_item(Item=item)

        return {
            'statusCode': 201,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'message': 'Patient created successfully',
                'patient': {
                    'patient_id': patient_id,
                    'name': name,
                    'email': email if email else None,
                    'phone': phone if phone else None,
                    'date_of_birth': date_of_birth if date_of_birth else None,
                    'created_at': timestamp
                }
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }