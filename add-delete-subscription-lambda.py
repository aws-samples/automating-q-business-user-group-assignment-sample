import boto3
import json
import os
import requests
from requests_aws4auth import AWS4Auth
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

session = boto3.Session()
credentials = session.get_credentials()
qclient = session.client('qbusiness')
ssoclient = session.client('sso-admin')

def lambda_handler(event, context):
   """
    Main Lambda handler function that processes HTTP requests for subscription management.
    Handles both POST (add subscription) and DELETE (remove subscription) operations.
    
    Args:
        event (dict): API Gateway event containing HTTP method, body, and query parameters
        context (object): Lambda context object
    
    Returns:
        dict: API Gateway response with status code, headers, and body
    """
    try:
        # Extract HTTP method
        http_method = event['httpMethod']
        
        # Parse body for POST requests
        body = {}
        if http_method == 'POST' and 'body' in event:
            body = json.loads(event['body'])
            
        # Extract query parameters for DELETE requests
        query_params = event.get('queryStringParameters', {}) or {}
        
        if http_method == 'POST':
            # Map to ADD action
            payload = {
                'action': 'ADD',
                'region': body.get('region'),
                'applicationId': body.get('applicationId'),
                'assignmentType': body.get('assignmentType'),
                'assignmentId': body.get('assignmentId'),
                'subscriptionType': body.get('subscriptionType')
            }
        elif http_method == 'DELETE':
            # Map to DELETE action
            payload = {
                'action': 'DELETE',
                'region': query_params.get('region'),
                'applicationId': query_params.get('applicationId'),
                'assignmentType': query_params.get('assignmentType'),
                'assignmentId': query_params.get('assignmentId')
            }
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Unsupported HTTP method'
                })
            }
        
        result = process_request(payload, context)
        
        # Return API Gateway response
        return {
            'statusCode': result['statusCode'],
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': result['body']
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e)
            })
        }


def process_request(event, context):
    try:
        # Extract parameters from the event
        region = event.get('region')
        action = event['action'] 
        applicationId = event['applicationId']
        assignmentType = event.get('assignmentType')
        assignmentId = event.get('assignmentId')
        subscriptionType = event.get('subscriptionType')
        subscriptionId = event.get('subscriptionId')
        logger.info(f"Event parameters - region: {region}, action: {action}, applicationId: {applicationId}, assignmentType: {assignmentType}, assignmentId: {assignmentId}, subscriptionType: {subscriptionType}, subscriptionId: {subscriptionId}")   

        # Validate action
        if action not in ['ADD', 'DELETE']:
            logger.error('Invalid action. Must be ADD, or DELETE')
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid action. Must be ADD, or DELETE'
                })
            }
        
        if action == 'ADD':
            # Validate required parameters for ADD
            if not all([applicationId, assignmentType, assignmentId, subscriptionType]):
                logger.error('assignmentType, assignmentId, and subscriptionType are required for ADD action')
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'assignmentType, assignmentId, and subscriptionType are required for ADD action'
                    })
                }

            # Validate subscription type
            if subscriptionType not in ['Q_BUSINESS', 'Q_LITE']:
                logger.error('Invalid subscription type. Must be Q_BUSINESS or Q_LITE')
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid subscription type. Must be Q_BUSINESS or Q_LITE'
                    })
                }

            # Validate assignment type
            if assignmentType not in ['GROUP', 'USER']:
                logger.error('Invalid assignment type. Must be GROUP or USER')
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid assignment type. Must be GROUP or USER'
                    })
                }
            
            # Add subscription
            result = add_subscription(
                region,
                applicationId,
                assignmentType,
                assignmentId,
                subscriptionType
            )
            logger.info(f"Subscription added successfully: {result}")
        
        else:  # DELETE
            if not all([applicationId, assignmentType, assignmentId]):
                logger.error('assignmentType and assignmentId are required for DELETE action')
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'assignmentType and assignmentId are required for DELETE action'
                    })
                }
                
            delete_subscription(
                region,
                applicationId,
                assignmentType,
                assignmentId
            )
            
            result = "{status:'Application assignment deleted successfully'}"
            logger.info(result)
        
        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }

def delete_subscription(region, applicationId, assignmentType, assignmentId):
    #First find the Subscription Id for the given Application and User/Group
    endpoint = f'https://qbusiness.{region}.api.aws/applications/{applicationId}/subscriptions'
    subscriptions_data = make_qbusiness_request(region, 'GET', endpoint)

    if 'subscriptions' not in subscriptions_data:
        logger.error("No subscriptions found for the given application")
        raise Exception(f"No subscriptions found for the given application")
        
    subscriptionId = ""
    for subscription in subscriptions_data['subscriptions']:
        principal = subscription.get('principal', {})
        if assignmentType.lower() in principal:
            if principal[assignmentType.lower()] == assignmentId:
                subscriptionId = subscription['subscriptionId']
                break
    if subscriptionId == "":
        logger.error("Subscription not found for the given application and principal")
        raise Exception(f"Subscription not found for the given application and principal")
    
    #Now call DELETE on the endpoint to delete
    endpoint += f"/{subscriptionId}"
    make_qbusiness_request(region, 'DELETE', endpoint)
    logger.info(f"Subscription deleted successfully: {subscriptionId}")
    #Remove IDC App assignment
    ssoclient.delete_application_assignment(
                ApplicationArn=qclient.get_application(applicationId=applicationId)["identityCenterApplicationArn"],
                PrincipalId=assignmentId,
                PrincipalType=assignmentType)
    logger.info(f"Application assignment deleted successfully: {assignmentId}")

def add_subscription(region, applicationId, assignmentType, assignmentId, subscriptionType):
    # Create IAM Identity Center application assignment
    app = qclient.get_application(applicationId=applicationId)
    ssoclient.create_application_assignment(
        ApplicationArn=app["identityCenterApplicationArn"],
        PrincipalId=assignmentId,
        PrincipalType=assignmentType
    )
    logger.info(f"Application assignment created successfully: {assignmentId}")
    
    endpoint = f'https://qbusiness.{region}.api.aws/applications/{applicationId}/subscriptions'
    
    payload = {
        'principal': {assignmentType.lower(): assignmentId}, 
        'type': subscriptionType
    }

    response = make_qbusiness_request(region, 'POST', endpoint, payload)
    logger.info(f"Subscription created successfully: {response}")
    return f"subscriptionId:{response['subscriptionId']}"

def make_qbusiness_request(region, method, endpoint, payload=None):
    headers = {
        'Content-Type': 'application/json'
    }

    try:
        aws_auth = AWS4Auth(
            credentials.access_key,
            credentials.secret_key,
            region,
            'qbusiness',
            session_token=credentials.token
        )

        response = requests.request(
            method=method,
            url=endpoint,
            auth=aws_auth,
            headers=headers,
            json=payload if payload else None,
            timeout=120
        )

        response.raise_for_status()
        logger.info(f"Request successful: {response.status_code}")
        return response.json()

    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")
