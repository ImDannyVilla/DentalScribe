import json
import boto3
import base64
import os
import httpx

secrets_client = boto3.client('secretsmanager')


def get_deepgram_key():
    """Retrieve Deepgram API key from Secrets Manager"""
    secret_arn = os.environ['DEEPGRAM_SECRET_ARN']
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response['SecretString'])
    return secret['api_key']


def lambda_handler(event, context):
    try:
        body = json.loads(event['body'])

        # Audio should be base64 encoded
        audio_data = base64.b64decode(body['audio'])

        # Get Deepgram API key
        api_key = get_deepgram_key()

        # Call Deepgram API directly with httpx
        url = 'https://api.deepgram.com/v1/listen'
        headers = {
            'Authorization': f'Token {api_key}',
            'Content-Type': 'audio/webm'
        }
        params = {
            'model': 'nova-2',
            'smart_format': 'true',
            'punctuate': 'true',
            'diarize': 'true',
            'language': 'en-US'
        }

        # Make request
        response = httpx.post(
            url,
            headers=headers,
            params=params,
            content=audio_data,
            timeout=30.0
        )

        if response.status_code != 200:
            raise Exception(f'Deepgram API error: {response.status_code} - {response.text}')

        result = response.json()
        transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
        confidence = result['results']['channels'][0]['alternatives'][0]['confidence']

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'transcript': transcript,
                'confidence': confidence
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