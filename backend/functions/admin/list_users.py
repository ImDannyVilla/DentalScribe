# functions/admin/list_users.py
import json
import boto3
import os
from security import format_response, format_error, require_admin, ValidationError

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ.get('USERS_TABLE', 'DentalScribeUsers-prod'))

USER_POOL_ID = os.environ.get('USER_POOL_ID')


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return format_response(200, {})

    try:
        # Admin only endpoint
        try:
            user_info = require_admin(event)
        except ValidationError as e:
            return format_error(403, e.message)

        # List users from Cognito
        try:
            users = []
            pagination_token = None

            while True:
                list_args = {'UserPoolId': USER_POOL_ID}
                if pagination_token:
                    list_args['PaginationToken'] = pagination_token
                
                response = cognito.list_users(**list_args)

                for user in response.get('Users', []):
                    user_data = {
                        'username': user.get('Username'),
                        'status': 'active' if user.get('UserStatus') == 'CONFIRMED' else 'pending',
                        'enabled': user.get('Enabled', True),
                        'created_at': user.get('UserCreateDate').isoformat() if user.get('UserCreateDate') else None
                    }

                    # Extract attributes
                    for attr in user.get('Attributes', []):
                        if attr['Name'] == 'email':
                            user_data['email'] = attr['Value']
                        elif attr['Name'] == 'name':
                            user_data['name'] = attr['Value']
                        elif attr['Name'] == 'custom:role':
                            user_data['role'] = attr['Value']
                        elif attr['Name'] == 'sub':
                            user_data['user_id'] = attr['Value']

                    # Default role if not set
                    if 'role' not in user_data:
                        user_data['role'] = 'user'

                    users.append(user_data)

                pagination_token = response.get('PaginationToken')
                if not pagination_token:
                    break
        except Exception as e:
            return format_error(500, "Failed to fetch users from directory", internal_error=e)

        # Sort by name/email
        users.sort(key=lambda u: u.get('name', u.get('email', '')).lower())

        return format_response(200, {
            'users': users,
            'count': len(users)
        })

    except Exception as e:
        return format_error(500, "An unexpected error occurred", internal_error=e)