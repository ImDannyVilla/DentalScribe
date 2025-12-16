# functions/admin/invite.py
import json
import boto3
import os
from datetime import datetime

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ.get('USERS_TABLE', 'DentalScribeUsers-prod'))

USER_POOL_ID = os.environ.get('USER_POOL_ID')


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': ''
        }

    try:
        # Verify admin role
        claims = event.get('requestContext', {}).get('authorizer', {}).get('claims', {})
        user_role = claims.get('custom:role', 'user')
        inviter_email = claims.get('email', 'unknown')

        if user_role != 'admin':
            return {
                'statusCode': 403,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Only admins can invite users'})
            }

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        email = body.get('email', '').strip().lower()
        name = body.get('name', '').strip()
        role = body.get('role', 'user')

        if not email:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Email is required'})
            }

        if not name:
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Name is required'})
            }

        # Validate role
        if role not in ['user', 'admin']:
            role = 'user'

        # Check if user already exists
        try:
            cognito.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=email
            )
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'User with this email already exists'})
            }
        except cognito.exceptions.UserNotFoundException:
            pass  # Good, user doesn't exist

        # Create user in Cognito with temporary password
        # Cognito will send an email with the temp password
        response = cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {'Name': 'email', 'Value': email},
                {'Name': 'email_verified', 'Value': 'true'},
                {'Name': 'name', 'Value': name},
                {'Name': 'custom:role', 'Value': role}
            ],
            DesiredDeliveryMediums=['EMAIL'],
            MessageAction='SUPPRESS'  # We'll send our own email or use Cognito's default
        )

        cognito_user = response.get('User', {})
        user_sub = None
        for attr in cognito_user.get('Attributes', []):
            if attr['Name'] == 'sub':
                user_sub = attr['Value']
                break

        # Store in DynamoDB
        timestamp = datetime.utcnow().isoformat()
        users_table.put_item(Item={
            'user_id': user_sub or email,
            'email': email,
            'name': name,
            'role': role,
            'status': 'pending',
            'invited_by': inviter_email,
            'invited_at': timestamp,
            'created_at': timestamp
        })

        # Send invitation email via Cognito (resend with RESEND action)
        try:
            cognito.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=email,
                MessageAction='RESEND'
            )
        except Exception as e:
            print(f"Could not resend invite email: {e}")

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'message': f'Invitation sent to {email}',
                'user': {
                    'email': email,
                    'name': name,
                    'role': role,
                    'status': 'pending'
                }
            })
        }

    except cognito.exceptions.UsernameExistsException:
        return {
            'statusCode': 400,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'User with this email already exists'})
        }
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }