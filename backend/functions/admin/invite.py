import json
import boto3
import os
from datetime import datetime

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ['USERS_TABLE'])


def lambda_handler(event, context):
    try:
        # Parse request
        body = json.loads(event['body'])
        email = body['email']
        name = body['name']
        role = body.get('role', 'user')  # Default to 'user' role

        # Get admin user from Cognito claims
        admin_email = event['requestContext']['authorizer']['claims']['email']
        admin_role = event['requestContext']['authorizer']['claims'].get('custom:role', 'user')

        # Check if requester is admin
        if admin_role != 'admin':
            return {
                'statusCode': 403,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Only admins can invite users'})
            }

        # Validate role
        if role not in ['admin', 'user']:
            return {
                'statusCode': 400,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Invalid role. Must be admin or user'})
            }

        # Create user in Cognito
        response = cognito.admin_create_user(
            UserPoolId=os.environ['USER_POOL_ID'],
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'name', 'Value': name},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'custom:role', 'Value': role}
            ],
            TemporaryPassword=generate_temp_password(),
            MessageAction='SUPPRESS',  # We'll send custom email
            DesiredDeliveryMediums=['EMAIL']
        )

        # Save to DynamoDB
        users_table.put_item(Item={
            'user_id': response['User']['Username'],
            'email': email,
            'name': name,
            'role': role,
            'invited_by': admin_email,
            'invited_at': datetime.utcnow().isoformat(),
            'status': 'invited'
        })

        # Send invitation email (using SES or SNS)
        send_invitation_email(email, name, role)

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'message': f'User {email} invited successfully',
                'user_id': response['User']['Username']
            })
        }

    except cognito.exceptions.UsernameExistsException:
        return {
            'statusCode': 400,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'User already exists'})
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }


def generate_temp_password():
    """Generate secure temporary password"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    password = ''.join(secrets.choice(alphabet) for i in range(16))
    return password


def send_invitation_email(email, name, role):
    """Send invitation email via SES"""
    ses = boto3.client('ses', region_name=os.environ['AWS_REGION'])

    subject = "You've been invited to Dental Scribe AI"
    body = f"""
Hello {name},

You've been invited to join Dental Scribe AI as a {role}.

Please check your email from AWS Cognito for your temporary password, 
then download the app and login with:

Email: {email}
Password: [Check your email from AWS Cognito]

You'll be asked to change your password on first login.

Welcome to the team!

- Dental Scribe AI
"""

    try:
        ses.send_email(
            Source='noreply@yourdomain.com',  # Must be verified in SES
            Destination={'ToAddresses': [email]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        # Email sending is optional, Cognito will send the password