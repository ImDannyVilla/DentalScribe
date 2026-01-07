# functions/patients/get.py
import json
import boto3
import os
from boto3.dynamodb.conditions import Key
from security import format_response, format_error

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('PATIENTS_TABLE', 'DentalScribePatients-prod'))


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {})

    try:
        # Get patient_id from path
        path_params = event.get('pathParameters') or {}
        patient_id = path_params.get('patient_id')

        if not patient_id:
            return format_error(400, "Patient ID is required")

        # Scan for patient by patient_id
        try:
            response = table.scan(
                FilterExpression=Key('patient_id').eq(patient_id)
            )
            items = response.get('Items', [])
        except Exception as e:
            return format_error(500, "Failed to fetch patient from database", internal_error=e)

        if not items:
            return format_error(404, "Patient not found")

        patient = items[0]

        return format_response(200, {
            'patient': {
                'patient_id': patient.get('patient_id'),
                'name': patient.get('name'),
                'email': patient.get('email'),
                'phone': patient.get('phone'),
                'date_of_birth': patient.get('date_of_birth'),
                'created_at': patient.get('created_at')
            }
        })

    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e)