import json
import boto3
import os
from datetime import datetime, timedelta

# Initialize clients
bedrock = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('NOTES_TABLE', 'DentalScribeNotes-prod'))

# Prompt optimized for Speaker labels (Provider vs Patient)
SYSTEM_PROMPT = """You are an expert Dental Scribe.
The transcript below identifies speakers (e.g., "Speaker 0", "Speaker 1").
- Contextually identify who is the Provider (Staff) and who is the Patient.
- Generate a structured SOAP note based on the conversation.

OUTPUT FORMAT:
VISIT SUMMARY:
[Brief summary of reason for visit and outcome]

SUBJECTIVE:
[Patient concerns, complaints, history of present illness]

OBJECTIVE:
[Clinical findings, exam results, specific teeth #, vitals]

ASSESSMENT & PLAN:
[Diagnosis, procedures performed, treatment planned, next steps]

CLINICAL CODES:
[Suggest likely CDT codes with brief descriptions]

PATIENT INSTRUCTIONS:
[Post-op instructions, hygiene recommendations, follow-up]
"""


def lambda_handler(event, context):
    try:
        # 1. Parse Input
        if 'body' in event and isinstance(event['body'], str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        transcript = body.get('transcript')
        patient_name = body.get('patient_name', 'UNKNOWN')

        if not transcript:
            return {'statusCode': 400, 'body': json.dumps({'error': 'No transcript provided'})}

        # 2. Get User Info (Safely)
        try:
            claims = event['requestContext']['authorizer']['claims']
            user_id = claims['sub']
            user_email = claims['email']
        except (KeyError, TypeError):
            user_id = "test-user"
            user_email = "test@example.com"

        # 3. Generate note using Bedrock
        bedrock_body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": f"{SYSTEM_PROMPT}\n\nTRANSCRIPT:\n{transcript}"
            }],
            "temperature": 0
        })

        # --- RESTORED: CLAUDE 4.5 HAIKU ID ---
        # This matches the ID you found in your playground
        haiku_4_5_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

        response = bedrock.invoke_model(
            modelId=os.environ.get('MODEL_ID', haiku_4_5_id),
            contentType='application/json',
            accept='application/json',
            body=bedrock_body
        )

        response_body = json.loads(response['body'].read())

        # Handle response format (some newer models put text in 'content')
        if 'content' in response_body:
            visit_summary = response_body['content'][0]['text']
        else:
            visit_summary = response_body.get('completion', '')

        # 4. Auto-save to DynamoDB
        timestamp = datetime.utcnow().isoformat()
        ttl = int((datetime.now() + timedelta(days=365)).timestamp())

        item = {
            'user_id': user_id,
            'timestamp': timestamp,
            'patient_name': patient_name,
            'transcript': transcript,
            'soap_note': visit_summary,
            'provider_email': user_email,
            'ttl': ttl,
            'created_at': timestamp
        }

        table.put_item(Item=item)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'note': visit_summary,
                'timestamp': timestamp,
                'note_id': f"{user_id}#{timestamp}",
                'saved': True
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        # Print the exact model ID we tried to use for debugging
        print(f"Attempted Model ID: {os.environ.get('MODEL_ID', 'Default')}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }