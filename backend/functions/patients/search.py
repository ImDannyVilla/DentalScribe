# functions/patients/search.py
import json
import boto3
import os
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('PATIENTS_TABLE', 'DentalScribePatients-prod'))


def get_cors_headers():
    return {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
    }


def levenshtein_distance(s1, s2):
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_match_score(query, name):
    """
    Calculate a match score. Lower is better.
    Returns tuple: (score, match_type)
    """
    query = query.lower()
    name_lower = name.lower()

    # Exact match
    if query == name_lower:
        return (0, 'exact')

    # Starts with
    if name_lower.startswith(query):
        return (1, 'starts_with')

    # Any word starts with query
    words = name_lower.split()
    for word in words:
        if word.startswith(query):
            return (1.5, 'word_starts_with')

    # Contains
    if query in name_lower:
        return (2, 'contains')

    # Fuzzy match on each word
    best_distance = float('inf')
    for word in words:
        if len(query) <= len(word):
            word_prefix = word[:len(query)]
            distance = levenshtein_distance(query, word_prefix)
            max_distance = max(1, len(query) // 3)
            if distance <= max_distance:
                best_distance = min(best_distance, 3 + distance)

        distance = levenshtein_distance(query, word)
        if distance <= max(2, len(word) // 3):
            best_distance = min(best_distance, 3 + distance)

    if best_distance < float('inf'):
        return (best_distance, 'fuzzy')

    return (100, 'none')


def lambda_handler(event, context):
    # Handle OPTIONS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': ''
        }

    try:
        # Get search query
        params = event.get('queryStringParameters') or {}
        query = params.get('q', '').strip()
        limit = int(params.get('limit', 20))

        if not query:
            return {
                'statusCode': 200,
                'headers': get_cors_headers(),
                'body': json.dumps({'patients': [], 'count': 0})
            }

        # Scan ALL patients (no practice_id filter for now)
        all_patients = []
        response = table.scan()
        all_patients.extend(response.get('Items', []))

        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            all_patients.extend(response.get('Items', []))

        print(f"Found {len(all_patients)} total patients in table")

        # Score and filter patients
        scored_patients = []
        for p in all_patients:
            name = p.get('name', '')
            if not name:
                continue

            score, match_type = fuzzy_match_score(query, name)

            if score < 100:
                scored_patients.append({
                    'patient': p,
                    'score': score,
                    'match_type': match_type
                })

        # Sort by score
        scored_patients.sort(key=lambda x: x['score'])
        top_patients = scored_patients[:limit]

        # Format response
        formatted_patients = []
        for item in top_patients:
            p = item['patient']
            formatted_patients.append({
                'patient_id': p.get('patient_id'),
                'name': p.get('name'),
                'email': p.get('email'),
                'phone': p.get('phone'),
                'date_of_birth': p.get('date_of_birth'),
                'created_at': p.get('created_at')
            })

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'patients': formatted_patients,
                'count': len(formatted_patients),
                'query': query
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': str(e)})
        }