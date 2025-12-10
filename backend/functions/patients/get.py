import json
import boto3
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['PATIENTS_TABLE'])


def lambda_handler(event, context):
    try:
        # Get user/practice ID from Cognito
        user_id = event['requestContext']['authorizer']['claims']['sub']
        practice_id = user_id

        # Get patient ID from path
        patient_id = event['pathParameters']['patient_id']

        response = table.get_item(
            Key={
                'practice_id': practice_id,
                'patient_id': patient_id
            }
        )

        patient = response.get('Item')

        if not patient:
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Patient not found'})
            }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'patient': patient})
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