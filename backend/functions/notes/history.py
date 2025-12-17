# functions/notes/history.py
import json
import boto3
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('NOTES_TABLE', 'DentalScribeNotes-prod'))


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
    }


def lambda_handler(event, context):
    try:
        # Handle OPTIONS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': get_cors_headers(),
                'body': ''
            }
        
        # Get user from Cognito
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_id = claims.get('sub')
        groups = claims.get('cognito:groups', [])
        user_role = 'admin' if ('Admin' in groups if isinstance(groups, list) else False) else 'user'
        
        if not user_id:
            return {
                'statusCode': 401,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Unauthorized'})
            }

        # Query parameters
        params = event.get('queryStringParameters') or {}
        limit = int(params.get('limit', 50))
        patient_id = params.get('patient_id')
        all_visits = params.get('all', 'false').lower() == 'true'

        # Determine if admin wants all visits
        is_admin_all_query = user_role == 'admin' and all_visits

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

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'notes': formatted_notes,
                'count': len(formatted_notes),
                'is_admin_view': is_admin_all_query
            }, default=str)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }
