import json
import boto3
import os

cognito = boto3.client('cognito-idp')


def lambda_handler(event, context):
    try:
        # Check if requester is admin
        admin_role = event['requestContext']['authorizer']['claims'].get('custom:role', 'user')

        if admin_role != 'admin':
            return {
                'statusCode': 403,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Only admins can list users'})
            }

        # List users from Cognito
        response = cognito.list_users(
            UserPoolId=os.environ['USER_POOL_ID'],
            Limit=60
        )

        users = []
        for user in response['Users']:
            user_data = {
                'username': user['Username'],
                'status': user['UserStatus'],
                'created': user['UserCreateDate'].isoformat(),
                'enabled': user['Enabled']
            }

            # Extract attributes
            for attr in user['Attributes']:
                if attr['Name'] == 'email':
                    user_data['email'] = attr['Value']
                elif attr['Name'] == 'name':
                    user_data['name'] = attr['Value']
                elif attr['Name'] == 'custom:role':
                    user_data['role'] = attr['Value']

            users.append(user_data)

        return {
            'statusCode': 200,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({
                'users': users,
                'count': len(users)
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }