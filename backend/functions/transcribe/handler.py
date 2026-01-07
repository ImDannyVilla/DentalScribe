import json
import boto3
import base64
import os
import httpx
from security import format_response, format_error, validate_input

secrets_client = boto3.client('secretsmanager')


def get_deepgram_key():
    """Retrieve Deepgram API key from Secrets Manager"""
    secret_arn = os.environ['DEEPGRAM_SECRET_ARN']
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret = json.loads(response['SecretString'])
    return secret['api_key']


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {}, method='POST')

    try:
        # 1. Parse and Validate Input
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return format_error(400, "Invalid JSON in request body", method='POST')

        is_valid, error_msg = validate_input(body, ['audio'])
        if not is_valid:
            return format_error(400, error_msg, method='POST')

        # 2. Process Audio
        try:
            audio_data = base64.b64decode(body['audio'])
        except Exception:
            return format_error(400, "Invalid base64 encoding for audio", method='POST')

        # 3. Get Deepgram API key
        try:
            api_key = get_deepgram_key()
        except Exception as e:
            return format_error(500, "Failed to retrieve API key", internal_error=e, method='POST')

        # 4. Call Deepgram API
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
            return format_error(response.status_code, f"Transcription service error: {response.status_code}", internal_error=response.text, method='POST')

        result = response.json()
        transcript = result['results']['channels'][0]['alternatives'][0]['transcript']
        confidence = result['results']['channels'][0]['alternatives'][0]['confidence']

        return format_response(200, {
            'transcript': transcript,
            'confidence': confidence
        }, method='POST')

    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e, method='POST')