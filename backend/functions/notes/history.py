# functions/notes/history.py
import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from security import format_response, format_error, get_user_info, ValidationError

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('NOTES_TABLE', 'DentalScribeNotes-prod'))


def lambda_handler(event, context):
    try:
        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return format_response(200, {})
        
        # Get user info from Cognito
        try:
            user_info = get_user_info(event)
            user_id = user_info['user_id']
            user_role = 'admin' if user_info['is_admin'] else 'user'
        except ValidationError:
            return format_error(401, "Unauthorized")

        # Query parameters
        params = event.get('queryStringParameters') or {}
        try:
            limit = int(params.get('limit', 50))
        except (ValueError, TypeError):
            limit = 50
            
        patient_id = params.get('patient_id')
        all_visits = params.get('all', 'false').lower() == 'true'

        # Determine if admin wants all visits
        is_admin_all_query = user_role == 'admin' and all_visits

        try:
            if patient_id:
                # Query by patient (uses GSI)
                response = table.query(
                    IndexName='patient-index',
                    KeyConditionExpression=Key('patient_id').eq(patient_id),
                    Limit=limit,
                    ScanIndexForward=False  # Most recent first
                )
                notes = response.get('Items', [])
                
                # If not admin, filter to only user's notes
                if not is_admin_all_query:
                    notes = [n for n in notes if n.get('user_id') == user_id]
                    
            elif is_admin_all_query:
                # Admin requesting all visits - use scan
                response = table.scan(Limit=limit)
                notes = response.get('Items', [])
                
                # Sort by timestamp descending
                notes.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
                
            else:
                # Regular user - query by their user_id
                response = table.query(
                    KeyConditionExpression=Key('user_id').eq(user_id),
                    Limit=limit,
                    ScanIndexForward=False
                )
                notes = response.get('Items', [])
        except Exception as e:
            return format_error(500, "Failed to fetch notes from database", internal_error=e)

        # Remove sensitive fields if needed and format response
        formatted_notes = []
        for note in notes:
            formatted_note = {
                'user_id': note.get('user_id'),
                'timestamp': note.get('timestamp'),
                'patient_name': note.get('patient_name', 'Unknown'),
                'patient_id': note.get('patient_id'),
                'soap_note': note.get('soap_note', ''),
                'transcript': note.get('transcript', ''),
                'template_name': note.get('template_name', 'Unknown'),
                'provider_email': note.get('provider_email', ''),
                'created_at': note.get('created_at', note.get('timestamp'))
            }
            formatted_notes.append(formatted_note)

        return format_response(200, {
            'notes': formatted_notes,
            'count': len(formatted_notes),
            'is_admin_view': is_admin_all_query
        })

    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e)
