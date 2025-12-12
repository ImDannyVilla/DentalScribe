# functions/notes/history.py
import json
import boto3
import os
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['NOTES_TABLE'])


def lambda_handler(event, context):
    try:
        # Get user from Cognito
        user_id = event['requestContext']['authorizer']['claims']['sub']

        # Query parameters
        params = event.get('queryStringParameters') or {}
        limit = int(params.get('limit', 50))
        patient_id = params.get('patient_id')

        # Query DynamoDB
        if patient_id:
            # Query by patient
            response = table.query(
                IndexName='patient-index',
                KeyConditionExpression=Key('patient_id').eq(patient_id),
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )
        else:
            # Query by user
            response = table.query(
                KeyConditionExpression=Key('user_id').eq(user_id),
                Limit=limit,
                ScanIndexForward=False
            )

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'notes': response['Items'],
                'count': len(response['Items'])
            }, default=str)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }