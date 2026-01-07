# functions/admin/invite.py
import json
import boto3
import os
import logging
from datetime import datetime
from security import (
    format_response,
    format_error,
    validate_input,
    require_admin,
    ValidationError
)

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ.get('USERS_TABLE', 'DentalScribeUsers-prod'))

USER_POOL_ID = os.environ.get('USER_POOL_ID')

# Cognito group names (must match groups created in Cognito)
ADMIN_GROUP = 'Admin'
STANDARD_GROUP = 'Standard'


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {}, method='POST')

    try:
        # Check admin access from Cognito groups
        try:
            user_info = require_admin(event)
            inviter_email = user_info['email']
        except ValidationError as e:
            return format_error(403, e.message, method='POST')

        # Parse and Validate request body
        try:
            body = json.loads(event.get('body', '{}'))
        except json.JSONDecodeError:
            return format_error(400, "Invalid JSON in request body", method='POST')
            
        is_valid, error_msg = validate_input(body, ['email', 'name'])
        if not is_valid:
            return format_error(400, error_msg, method='POST')

        email = body.get('email', '').strip().lower()
        name = body.get('name', '').strip()
        role = body.get('role', 'user')

        # Validate role
        if role not in ['user', 'admin']:
            role = 'user'

        # Check if user already exists
        try:
            cognito.admin_get_user(
                UserPoolId=USER_POOL_ID,
                Username=email
            )
            return format_error(400, "User with this email already exists", method='POST')
        except cognito.exceptions.UserNotFoundException:
            pass  # Good, user doesn't exist
        except Exception as e:
            logger.error(f"Error checking user existence: {e}")
            return format_error(500, "Failed to check user existence", internal_error=e, method='POST')

        # Create user in Cognito
        try:
            response = cognito.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=email,
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'email_verified', 'Value': 'true'},
                    {'Name': 'name', 'Value': name},
                    {'Name': 'custom:role', 'Value': role}  # Keep for backwards compatibility
                ],
                DesiredDeliveryMediums=['EMAIL'],
                MessageAction='SUPPRESS'
            )
            logger.info(f"Created Cognito user: {email}")
        except cognito.exceptions.UsernameExistsException:
            return format_error(400, "User with this email already exists", method='POST')
        except Exception as e:
            logger.error(f"Error creating Cognito user: {e}")
            return format_error(500, "Failed to create user in identity provider", internal_error=e, method='POST')

        # Extract user sub (unique ID)
        cognito_user = response.get('User', {})
        user_sub = None
        for attr in cognito_user.get('Attributes', []):
            if attr['Name'] == 'sub':
                user_sub = attr['Value']
                break

        # Add user to appropriate Cognito group
        group_name = ADMIN_GROUP if role == 'admin' else STANDARD_GROUP
        group_assigned = False
        try:
            cognito.admin_add_user_to_group(
                UserPoolId=USER_POOL_ID,
                Username=email,
                GroupName=group_name
            )
            group_assigned = True
            logger.info(f"Added user {email} to group {group_name}")
        except cognito.exceptions.ResourceNotFoundException:
            logger.error(f"Cognito group '{group_name}' does not exist. Please create it in the Cognito console.")
        except Exception as e:
            logger.error(f"Failed to add user to group {group_name}: {e}")

        # Store in DynamoDB
        try:
            timestamp = datetime.utcnow().isoformat()
            users_table.put_item(Item={
                'user_id': user_sub or email,
                'email': email,
                'name': name,
                'role': role,
                'cognito_group': group_name,
                'group_assigned': group_assigned,
                'status': 'pending',
                'invited_by': inviter_email,
                'invited_at': timestamp,
                'created_at': timestamp
            })
            logger.info(f"Saved user to DynamoDB: {email}")
        except Exception as e:
            logger.error(f"Error saving user to DynamoDB: {e}")

        # Send invitation email
        try:
            cognito.admin_create_user(
                UserPoolId=USER_POOL_ID,
                Username=email,
                MessageAction='RESEND'
            )
            logger.info(f"Sent invitation email to: {email}")
        except Exception as e:
            logger.warning(f"Could not resend invite email: {e}")

        return format_response(200, {
            'message': f'Invitation sent to {email}',
            'user': {
                'email': email,
                'name': name,
                'role': role,
                'group': group_name,
                'group_assigned': group_assigned,
                'status': 'pending'
            }
        }, method='POST')

    except Exception as e:
        logger.error(f"Unexpected error in invite handler: {e}", exc_info=True)
        return format_error(500, "An unexpected error occurred", internal_error=e, method='POST')