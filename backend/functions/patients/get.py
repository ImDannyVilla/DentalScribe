# functions/patients/get.py
import json
import boto3
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('PATIENTS_TABLE', 'DentalScribePatients-prod'))


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
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
        # Get patient_id from path
        path_params = event.get('pathParameters') or {}
        patient_id = path_params.get('patient_id')

        if not patient_id:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Patient ID is required'})
            }

        # Scan for patient by patient_id (since we might not know practice_id)
        response = table.scan(
            FilterExpression=Key('patient_id').eq(patient_id)
        )

        items = response.get('Items', [])

        if not items:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Patient not found'})
            }

        patient = items[0]

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'patient': {
                    'patient_id': patient.get('patient_id'),
                    'name': patient.get('name'),
                    'email': patient.get('email'),
                    'phone': patient.get('phone'),
                    'date_of_birth': patient.get('date_of_birth'),
                    'created_at': patient.get('created_at')
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