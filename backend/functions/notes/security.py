import json
import os
import traceback

def get_allowed_origins():
    """Get allowed origins from environment or use defaults."""
    env_origins = os.environ.get('ALLOWED_ORIGINS', '')
    if env_origins:
        return [o.strip() for o in env_origins.split(',')]
    
    # Default for development
    return [
        'http://localhost:5173',
        'http://localhost:3000',
    ]

ALLOWED_ORIGINS = get_allowed_origins()

def get_cors_headers(method='GET'):
    """Generate CORS headers for responses."""
    # In production, we should ideally echo the request origin if it matches our allowlist
    # For now, we'll use the first allowed origin or '*'
    origin = ALLOWED_ORIGINS[0] if ALLOWED_ORIGINS else '*'
    
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': f'{method},OPTIONS'
    }

def format_response(status_code, body, method='GET'):
    """Format a consistent API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': get_cors_headers(method),
        'body': json.dumps(body)
    }

def format_error(status_code, message, internal_error=None, method='GET'):
    """Format a secure error response, masking internal details in production."""
    is_prod = os.environ.get('STAGE') == 'prod'
    
    response_body = {
        'error': message
    }
    
    if internal_error and not is_prod:
        response_body['details'] = str(internal_error)
        response_body['trace'] = traceback.format_exc()
        
    if internal_error:
        print(f"Error: {message} | Internal Error: {str(internal_error)}")
    else:
        print(f"Error: {message}")
        
    return format_response(status_code, response_body, method)

def validate_input(data, required_fields):
    """Validate that required fields are present in the input data."""
    if not data:
        return False, "Missing request body"
    
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    return True, None

class ValidationError(Exception):
    """Custom exception for validation errors."""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

def get_user_info(event):
    """
    Extract user info from Cognito authorizer claims.
    Returns dict with user_id, email, and is_admin.
    """
    try:
        # Support both REST API and HTTP API authorizer formats
        rc = event.get('requestContext', {})
        authorizer = rc.get('authorizer', {}) or {}
        claims = authorizer.get('claims') or authorizer.get('jwt', {}).get('claims') or {}
        
        if not claims:
            raise ValidationError('Authentication required')
            
        user_id = claims.get('sub')
        email = claims.get('email') or claims.get('cognito:username') or 'unknown@example.com'
        
        # Get groups from token
        groups_raw = claims.get('cognito:groups', [])
        
        # Handle groups as string or list
        groups = []
        if isinstance(groups_raw, str):
            try:
                groups = json.loads(groups_raw)
            except:
                groups = [g.strip() for g in groups_raw.split(',')]
        elif isinstance(groups_raw, list):
            groups = groups_raw
        
        # Check if user is in Admin group
        is_admin = any(
            str(g).strip().lower() == 'admin' 
            for g in groups
        )
        
        return {
            'user_id': user_id,
            'email': email,
            'is_admin': is_admin,
            'groups': groups
        }
    except ValidationError:
        raise
    except (KeyError, TypeError) as e:
        raise ValidationError('Authentication required')


def require_admin(event):
    """
    Check if user is admin. Raises ValidationError if not.
    Returns user_info if admin.
    """
    user_info = get_user_info(event)
    
    if not user_info['is_admin']:
        raise ValidationError('Admin access required')
    
    return user_info
