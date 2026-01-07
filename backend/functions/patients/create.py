# functions/patients/create.py
import json
import boto3
import os
import uuid
from datetime import datetime
from security import format_response, format_error, validate_input, get_user_info, ValidationError

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('PATIENTS_TABLE', 'DentalScribePatients-prod'))


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {}, method='POST')

    try:
        # Get user info from Cognito
        try:
            user_info = get_user_info(event)
            user_id = user_info['user_id']
        except ValidationError:
            user_id = 'unknown'

        # Use 'default' as practice_id for simplicity
        practice_id = 'default'

        # Parse and Validate request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return format_error(400, "Invalid JSON in request body", method='POST')
            
        is_valid, error_msg = validate_input(body, ['name'])
        if not is_valid:
            return format_error(400, error_msg, method='POST')

        name = body.get('name', '').strip()
        email = body.get('email', '').strip()
        phone = body.get('phone', '').strip()
        date_of_birth = body.get('date_of_birth', '').strip()

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

        try:
            table.put_item(Item=item)
        except Exception as e:
            return format_error(500, "Failed to save patient to database", internal_error=e, method='POST')

        return format_response(201, {
            'message': 'Patient created successfully',
            'patient': {
                'patient_id': patient_id,
                'name': name,
                'email': email if email else None,
                'phone': phone if phone else None,
                'date_of_birth': date_of_birth if date_of_birth else None,
                'created_at': timestamp
            }
        }, method='POST')

    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e, method='POST')