# functions/generate/handler.py
import json
import boto3
import os
import re
from datetime import datetime, timedelta
from security import format_response, format_error, validate_input, get_user_info, ValidationError

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

IMPORTANT: Format your output EXACTLY like the example below. Match the section headers, style, and level of detail shown in the example. Output the final note in plain text format only. Do NOT use any Markdown formatting (no # headers, no **bold**, no _italics_, no links, no tables) and do NOT use code fences or backticks. Use standard capitalization and indentation for structure. If the transcript or template hints at Markdown, normalize it to plain text with simple "- " bullets only where appropriate.

===== EXAMPLE FORMAT =====
{example}
===== END EXAMPLE =====

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
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {}, method='POST')

    try:
        # 1. Parse and Validate Input
        try:
            if 'body' in event and isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event.get('body', {})
        except json.JSONDecodeError:
            return format_error(400, "Invalid JSON in request body", method='POST')

        is_valid, error_msg = validate_input(body, ['transcript'])
        if not is_valid:
            return format_error(400, error_msg, method='POST')

        transcript = body.get('transcript')
        patient_name = body.get('patient_name', 'UNKNOWN')
        template_id = body.get('template_id', 'default_soap')

        # 2. Get User Info (Safely)
        try:
            user_info = get_user_info(event)
            user_id = user_info['user_id']
            user_email = user_info['email']
        except ValidationError:
            # Fallback for testing/dev if no authorizer
            user_id = "test-user"
            user_email = "test@example.com"

        # 3. Fetch the template
        try:
            template = get_template(template_id)
        except Exception as e:
            return format_error(500, "Failed to fetch template", internal_error=e, method='POST')
        
        # 4. Build the prompt
        system_prompt = build_prompt(template, transcript, patient_name)

        # 5. Generate note using Bedrock
        try:
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
        except Exception as e:
            return format_error(500, "Failed to generate note via AI", internal_error=e, method='POST')

        # Sanitize Markdown to ensure plain text output
        txt = visit_summary or ""
        # Remove fenced code blocks (``` or ~~~)
        txt = re.sub(r"```(?:\\w+)?\n?([\s\S]*?)\n?```", r"\\1", txt)
        txt = re.sub(r"~~~(?:\\w+)?\n?([\s\S]*?)\n?~~~", r"\\1", txt)
        # Inline code backticks
        txt = re.sub(r"`([^`]+)`", r"\\1", txt)
        # Headers and blockquotes
        txt = re.sub(r"^[ \t]{0,3}#{1,6}[ \t]*", "", txt, flags=re.MULTILINE)
        txt = re.sub(r"^[ \t]*>[ \t]?", "", txt, flags=re.MULTILINE)
        # Images and links
        txt = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\\1", txt)
        txt = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\\1", txt)
        # Bold/italic emphasis
        txt = re.sub(r"\*\*([^*]+)\*\*", r"\\1", txt)
        txt = re.sub(r"__([^_]+)__", r"\\1", txt)
        txt = re.sub(r"_([^_]+)_", r"\\1", txt)
        txt = re.sub(r"\*([^*]+)\*", r"\\1", txt)
        # Normalize bullet markers to '- ' (keep numeric lists as-is)
        txt = re.sub(r"^[ \t]*[\*\+-][ \t]+", "- ", txt, flags=re.MULTILINE)
        # Horizontal rules
        txt = re.sub(r"^[ \t]*([-*_]){3,}[ \t]*$", "", txt, flags=re.MULTILINE)
        # Remove table border pipes at line start/end
        txt = re.sub(r"^\|", "", txt, flags=re.MULTILINE)
        txt = re.sub(r"\|$", "", txt, flags=re.MULTILINE)
        # Collapse excessive blank lines and trim
        txt = re.sub(r"\n\s*\n\s*\n+", "\n\n", txt)
        txt = re.sub(r"[ \t]+$", "", txt, flags=re.MULTILINE)
        visit_summary = txt.strip()

        # 6. Auto-save to DynamoDB
        try:
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
        except Exception as e:
            # We still return the note even if save fails, but log it
            print(f"Error saving to DynamoDB: {str(e)}")

        return format_response(200, {
            'note': visit_summary,
            'timestamp': timestamp if 'timestamp' in locals() else None,
            'note_id': f"{user_id}#{timestamp}" if 'timestamp' in locals() else None,
            'template_used': template.get('name', 'Unknown'),
            'saved': 'timestamp' in locals()
        }, method='POST')

    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e, method='POST')
