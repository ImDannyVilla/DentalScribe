# functions/admin/list_users.py
import json
import boto3
import os

cognito = boto3.client('cognito-idp')
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(os.environ.get('USERS_TABLE', 'DentalScribeUsers-prod'))

USER_POOL_ID = os.environ.get('USER_POOL_ID')


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
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
        groups = claims.get('cognito:groups', [])
        is_admin = 'Admin' in groups if isinstance(groups, list) else False

        if not is_admin:
            return {
                'statusCode': 403,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Only admins can view users'})
            }

        # List users from Cognito
        users = []
        pagination_token = None

        while True:
            if pagination_token:
                response = cognito.list_users(
                    UserPoolId=USER_POOL_ID,
                    PaginationToken=pagination_token
                )
            else:
                response = cognito.list_users(
                    UserPoolId=USER_POOL_ID
                )

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

        # Sort by name/email
        users.sort(key=lambda u: u.get('name', u.get('email', '')).lower())

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'users': users,
                'count': len(users)
            }, default=str)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }