import json
import boto3
import os
import uuid
from datetime import datetime

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['PATIENTS_TABLE'])


def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])

        # Get user/practice ID from Cognito
        user_id = event['requestContext']['authorizer']['claims']['sub']
        practice_id = user_id

        # Validate required fields
        name = body.get('name', '').strip()
        if not name:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Patient name is required'})
            }

        # Generate patient ID
        patient_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Create patient record
        item = {
            'practice_id': practice_id,
            'patient_id': patient_id,
            'name': name,
            'name_lowercase': name.lower(),
            'created_at': timestamp,
            'updated_at': timestamp,
            'created_by': user_id
        }

        # Optional fields
        if 'phone' in body:
            item['phone'] = body['phone']
        if 'email' in body:
            item['email'] = body['email']
        if 'notes' in body:
            item['notes'] = body['notes']

        table.put_item(Item=item)

        return {
            'statusCode': 201,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'patient': item,
                'message': 'Patient created successfully'
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }