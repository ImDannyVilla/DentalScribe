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
        practice_id = user_id  # Each user's practice

        # Get search query
        query = event.get('queryStringParameters', {}).get('q', '').strip().lower()

        if not query:
            # Return all patients for this practice
            response = table.query(
                KeyConditionExpression=Key('practice_id').eq(practice_id),
                Limit=50
            )
        else:
            # Search by name
            response = table.query(
                IndexName='name-search-index',
                KeyConditionExpression=Key('practice_id').eq(practice_id) & Key('name_lowercase').begins_with(query),
                Limit=20
            )

        patients = response.get('Items', [])

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'patients': patients,
                'count': len(patients)
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