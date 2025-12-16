# functions/generate/handler.py
import json
import boto3
import os
from datetime import datetime, timedelta

# Initialize clients
bedrock = boto3.client('bedrock-runtime', region_name=os.environ.get('AWS_REGION', 'us-east-1'))
dynamodb = boto3.resource('dynamodb')
notes_table = dynamodb.Table(os.environ.get('NOTES_TABLE', 'DentalScribeNotes-prod'))
templates_table = dynamodb.Table(os.environ.get('TEMPLATES_TABLE', 'DentalScribeTemplates-prod'))

# Default templates (same as in templates handler)
DEFAULT_TEMPLATES = {
    'default_soap': {
        'name': 'SOAP General',
        'example_output': '''SUBJECTIVE:
Patient presents for [reason]. Reports [symptoms/concerns].

OBJECTIVE:
Exam findings: [clinical observations]
Teeth examined: [tooth numbers]
Radiographs: [if applicable]

ASSESSMENT:
[Diagnosis and clinical impression]

PLAN:
1. [Treatment performed]
2. [Follow-up recommendations]
3. [Next appointment]'''
    },
    'default_hygiene': {
        'name': 'Hygiene Recall',
        'example_output': '''SUBJECTIVE:
Patient presents for routine prophylaxis. [Any concerns reported]

OBJECTIVE:
Probing depths: [findings]
Bleeding on probing: [yes/no, locations]
Plaque score: [percentage]
Calculus: [light/moderate/heavy]

ASSESSMENT:
[Periodontal status]

PLAN:
1. Prophylaxis completed
2. Fluoride treatment: [yes/no]
3. OHI provided
4. Return in [timeframe]'''
    },
    'default_limited': {
        'name': 'Limited Exam (Emergency)',
        'example_output': '''CHIEF COMPLAINT:
[Patient's primary concern in their words]

HISTORY OF PRESENT ILLNESS:
Onset: [when symptoms started]
Duration: [how long]
Character: [sharp/dull/throbbing]
Location: [specific tooth/area]
Aggravating factors: [hot/cold/biting]
Relieving factors: [what helps]

CLINICAL FINDINGS:
[Exam observations]

RADIOGRAPHIC FINDINGS:
[X-ray interpretation]

DIAGNOSIS:
[Clinical diagnosis]

TREATMENT PROVIDED:
[Procedures performed today]

RECOMMENDATIONS:
[Follow-up care needed]'''
    }
}


def get_template(template_id):
    """Fetch template by ID - check defaults first, then DynamoDB"""
    
    # Check if it's a default template
    if template_id in DEFAULT_TEMPLATES:
        return DEFAULT_TEMPLATES[template_id]
    
    # Try to fetch from DynamoDB
    try:
        response = templates_table.get_item(Key={'template_id': template_id})
        template = response.get('Item')
        if template:
            return {
                'name': template.get('name', 'Custom Template'),
                'example_output': template.get('example_output', '')
            }
    except Exception as e:
        print(f"Error fetching template: {str(e)}")
    
    # Fallback to default SOAP
    return DEFAULT_TEMPLATES['default_soap']


def build_prompt(template, transcript, patient_name):
    """Build the prompt for Bedrock using the template's example output"""
    
    example = template.get('example_output', '')
    template_name = template.get('name', 'Clinical Note')
    
    system_prompt = f"""You are an expert Dental Scribe AI.

Your task is to generate a clinical note from a conversation transcript.

IMPORTANT: Format your output EXACTLY like the example below. Match the section headers, style, and level of detail shown in the example.

===== EXAMPLE FORMAT =====
{example}
===== END EXAMPLE =====

The transcript may identify speakers (e.g., "Speaker 0", "Speaker 1"). Contextually determine who is the Provider and who is the Patient.

Generate a note for patient "{patient_name}" following the exact format shown above.

Key guidelines:
- Use the same section headers as the example
- Match the formatting style (bullets, numbering, etc.)
- Include relevant clinical details from the transcript
- Be concise but thorough
- Use proper dental terminology
- Include specific tooth numbers when mentioned
- Note any procedures performed or recommended
"""

    return system_prompt


def lambda_handler(event, context):
    try:
        # 1. Parse Input
        if 'body' in event and isinstance(event['body'], str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        transcript = body.get('transcript')
        patient_name = body.get('patient_name', 'UNKNOWN')
        template_id = body.get('template_id', 'default_soap')

        if not transcript:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No transcript provided'})
            }

        # 2. Get User Info (Safely)
        try:
            claims = event['requestContext']['authorizer']['claims']
            user_id = claims['sub']
            user_email = claims['email']
        except (KeyError, TypeError):
            user_id = "test-user"
            user_email = "test@example.com"

        # 3. Fetch the template
        template = get_template(template_id)
        
        # 4. Build the prompt
        system_prompt = build_prompt(template, transcript, patient_name)

        # 5. Generate note using Bedrock
        bedrock_body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "messages": [{
                "role": "user",
                "content": f"{system_prompt}\n\nTRANSCRIPT:\n{transcript}"
            }],
            "temperature": 0.1
        })

        # Use Claude Haiku for fast, cost-effective generation
        model_id = os.environ.get('MODEL_ID', 'us.anthropic.claude-haiku-4-5-20251001-v1:0')

        response = bedrock.invoke_model(
            modelId=model_id,
            contentType='application/json',
            accept='application/json',
            body=bedrock_body
        )

        response_body = json.loads(response['body'].read())

        # Handle response format
        if 'content' in response_body:
            visit_summary = response_body['content'][0]['text']
        else:
            visit_summary = response_body.get('completion', '')

        # 6. Auto-save to DynamoDB
        timestamp = datetime.utcnow().isoformat()
        ttl = int((datetime.now() + timedelta(days=365)).timestamp())

        item = {
            'user_id': user_id,
            'timestamp': timestamp,
            'patient_name': patient_name,
            'patient_id': body.get('patient_id'),
            'transcript': transcript,
            'soap_note': visit_summary,
            'template_id': template_id,
            'template_name': template.get('name', 'Unknown'),
            'provider_email': user_email,
            'ttl': ttl,
            'created_at': timestamp
        }

        notes_table.put_item(Item=item)

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
                'template_used': template.get('name', 'Unknown'),
                'saved': True
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
