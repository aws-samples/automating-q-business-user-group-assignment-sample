import boto3
import requests
from requests_aws4auth import AWS4Auth
import json
import os
import logging

session = boto3.Session()
credentials = session.get_credentials()
qclient = session.client('qbusiness')
ssoclient = session.client('sso-admin')

# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    AWS Lambda handler for managing Q Business subscriptions.
    
    Supports two operations:
    - ADD: Creates a new subscription and IAM Identity Center application assignment
    - DELETE: Removes an existing subscription and application assignment
    
    Args:
        event (dict): Lambda event containing:
            - region (str): AWS region
            - action (str): ADD, DELETE
            - applicationId (str): Q Business application ID
            - assignmentType (str): GROUP or USER (required for ADD/DELETE)
            - assignmentId (str): Group or user ID (required for ADD/DELETE)
            - subscriptionType (str): Q_BUSINESS or Q_LITE (required for ADD)
        context (LambdaContext): Lambda context object
        
    Returns:
        dict: Response containing statusCode and body
            Success: {'statusCode': 200, 'body': result}
            Error: {'statusCode': 400/500, 'body': {'error': error_message}}
    """
    try:
        # Extract parameters from the event
        region = event.get('region')
        action = event['action'] 
        applicationId = event['applicationId']
        assignmentType = event.get('assignmentType')
        assignmentId = event.get('assignmentId')
        subscriptionType = event.get('subscriptionType')

        # Validate action
        if action not in ['ADD', 'DELETE']:
            logger.error(f"Invalid action: {action}")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid action. Must be ADD, or DELETE'
                })
            }
        
        if action == 'ADD':
            # Validate required parameters for ADD
            if not all([applicationId, assignmentType, assignmentId, subscriptionType]):
                logger.error(f"Missing required parameters for ADD action")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'assignmentType, assignmentId, and subscriptionType are required for ADD action'
                    })
                }

            # Validate subscription type
            if subscriptionType not in ['Q_BUSINESS', 'Q_LITE']:
                logger.error(f"Invalid subscription type: {subscriptionType}")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid subscription type. Must be Q_BUSINESS or Q_LITE'
                    })
                }

            # Validate assignment type
            if assignmentType not in ['GROUP', 'USER']:
                logger.error(f"Invalid assignment type: {assignmentType}")
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
                logger.error(f"Missing required parameters for DELETE action")
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'applicationId, assignmentType and assignmentId are required for DELETE action'
                    })
                }
                
            
            delete_subscription(
                region,
                applicationId,
                assignmentType,
                assignmentId
            )
            
            result = "Application assignment deleted successfully"
            logger.info(f"Application assignment deleted successfully {applicationId} {assignmentId}")
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
    """
    Delete subscription details for a given application and subscription.

    Args:
        region (str): The AWS region where the application is located
        applicationId (str): The unique identifier of the Q Business application
        assignmentType (str): GROUP or USER 
        assignmentId (str): Group or user ID 
    
    Returns:
        dict: Response containing status message and details

    """

    logger.info(f"Deleting subscription for application {applicationId}")
    #First find the Subscription Id for the given Application and User/Group
    endpoint = f'https://qbusiness.{region}.api.aws/applications/{applicationId}/subscriptions'
    subscriptions_data = make_qbusiness_request(region, 'GET', endpoint)

    if 'subscriptions' not in subscriptions_data:
        logger.error(f"No subscriptions found for the given application")
        raise Exception(f"No subscriptions found for the given application")
        
    subscriptionId = ""
    for subscription in subscriptions_data['subscriptions']:
        principal = subscription.get('principal', {})
        if assignmentType.lower() in principal:
            if principal[assignmentType.lower()] == assignmentId:
                subscriptionId = subscription['subscriptionId']
                break
    if subscriptionId == "":
        logger.error(f"Subscription not found for the given application and principal")
        raise Exception(f"Subscription not found for the given application and principal")
            if principal[assignmentType.lower()] == assignmentId:
    logger.info(f"Subscription found for the given application and principal  {applicationId} {assignmentId}")  

    #Now call DELETE on the endpoint to delete
    make_qbusiness_request(region, 'DELETE', f"{endpoint}/{subscriptionId}")
    #Remove IDC App assignment
    logger.info(f"Deleting application assignment for application {applicationId}")
    ssoclient.delete_application_assignment(
                ApplicationArn=qclient.get_application(applicationId=applicationId)["identityCenterApplicationArn"],
                PrincipalId=assignmentId,
                PrincipalType=assignmentType)
    logger.info(f"Application assignment deleted successfully")
    return {
        'subscriptionId': subscriptionId,
        'message': 'Subscription and application assignment deleted successfully'
    }
    

def add_subscription(region, applicationId, assignmentType, assignmentId, subscriptionType):
    """
    Adds the subscription type for a given application and group/user.

    Args:
        region (str): The AWS region where the application is located
        applicationId (str): The unique identifier of the Q Business application
        assignmentType (str): GROUP or USER
        assignmentId (str): Group or user ID
        subscriptionType (str): Q_BUSINESS or Q_LITE
    """
    logger.info(f"Adding subscription for application {applicationId}") 
    # Create IAM Identity Center application assignment
    app = qclient.get_application(applicationId=applicationId)
    ssoclient.create_application_assignment(
        ApplicationArn=app["identityCenterApplicationArn"],
        PrincipalId=assignmentId,
        PrincipalType=assignmentType
    )
    logger.info(f"Application assignment created successfully {applicationId}")
    
    endpoint = f'https://qbusiness.{region}.api.aws/applications/{applicationId}/subscriptions'
    
    payload = {
        'principal': {assignmentType.lower(): assignmentId}, 
        'type': subscriptionType
    }

    response = make_qbusiness_request(region, 'POST', endpoint, payload)
    logger.info(f"Subscription created successfully {subscriptionId}")
    return response["subscriptionId"]

def make_qbusiness_request(region, method, endpoint, payload=None):
    """
    Makes an authenticated request to Q Business API
    
    Args:
        region (str): AWS region
        method (str): HTTP method (GET, POST, etc)
        endpoint (str): Full API endpoint URL
        payload (dict, optional): Request payload for POST/PUT requests
    """
    headers = {
        'Content-Type': 'application/json'
    }
    logger.info(f"Making Q Business request to {endpoint}")
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
            data=json.dumps(payload) if payload else None,
            timeout=120
        )

        response.raise_for_status()
        logger.info(f"Q Business request successful")   
        return response.json()

    except requests.exceptions.RequestException as e:
        raise Exception(f"Request failed: {str(e)}")




