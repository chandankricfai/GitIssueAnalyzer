






"""
Scan Lambda Function - Fetch and cache GitHub issues

This Lambda function handles the POST /scan endpoint.
It fetches all open issues from a GitHub repository and stores them in DynamoDB.
"""

import json
import boto3
import requests
import os
from datetime import datetime
from typing import Dict, Any, List
import logging

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Initialize logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'github-issues')
SECRETS_NAME = os.environ.get('SECRETS_NAME', 'github-token')

# GitHub API configuration
GITHUB_API_BASE = 'https://api.github.com'
GITHUB_API_VERSION = 'application/vnd.github.v3+json'


def get_github_token() -> str:
    """
    Retrieve GitHub API token from AWS Secrets Manager.
    
    Returns:
        str: GitHub personal access token
        
    Raises:
        Exception: If token retrieval fails
    """
    try:
        response = secrets_client.get_secret_value(SecretId=SECRETS_NAME)
        if 'SecretString' in response:
            secret = json.loads(response['SecretString'])
            return secret.get('github_token')
        else:
            return response['SecretBinary']
    except Exception as e:
        logger.error(f"Failed to retrieve GitHub token: {str(e)}")
        raise


def fetch_github_issues(repo: str, token: str) -> List[Dict[str, Any]]:
    """
    Fetch all open issues from a GitHub repository.
    
    Args:
        repo: Repository in format "owner/repo-name"
        token: GitHub API token
        
    Returns:
        List of issue dictionaries
        
    Raises:
        ValueError: If repo format is invalid
        requests.RequestException: If API call fails
    """
    # Validate repo format
    if '/' not in repo or len(repo.split('/')) != 2:
        raise ValueError(f"Invalid repo format: {repo}. Expected 'owner/repo-name'")
    
    owner, repo_name = repo.split('/')
    
    headers = {
        'Authorization': f'token {token}',
        'Accept': GITHUB_API_VERSION,
        'User-Agent': 'GitHub-Issue-Analyzer'
    }
    
    issues = []
    page = 1
    per_page = 100  # Maximum per GitHub API
    
    try:
        while True:
            url = f"{GITHUB_API_BASE}/repos/{owner}/{repo_name}/issues"
            params = {
                'state': 'open',
                'per_page': per_page,
                'page': page,
                'sort': 'created',
                'direction': 'desc'
            }
            
            logger.info(f"Fetching page {page} of issues from {repo}")
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            
            page_issues = response.json()
            if not page_issues:
                break
            
            issues.extend(page_issues)
            page += 1
            
            # Stop if we've fetched all issues
            if len(page_issues) < per_page:
                break
                
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API error: {str(e)}")
        raise
    
    return issues


def extract_issue_data(issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract relevant fields from GitHub issue.
    
    Args:
        issue: Raw GitHub issue object
        
    Returns:
        Dictionary with extracted fields
    """
    return {
        'id': issue['id'],
        'number': issue['number'],
        'title': issue['title'],
        'body': issue['body'] or '',
        'html_url': issue['html_url'],
        'created_at': issue['created_at'],
        'updated_at': issue['updated_at'],
        'labels': [label['name'] for label in issue.get('labels', [])],
        'state': issue['state'],
        'cached_at': datetime.utcnow().isoformat()
    }


def cache_issues(repo: str, issues: List[Dict[str, Any]]) -> int:
    """
    Store issues in DynamoDB.
    
    Args:
        repo: Repository name
        issues: List of issue dictionaries
        
    Returns:
        Number of issues cached
        
    Raises:
        Exception: If DynamoDB operation fails
    """
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    
    cached_count = 0
    
    try:
        with table.batch_writer(batch_size=25) as batch:
            for issue in issues:
                issue_data = extract_issue_data(issue)
                
                # Use repo as partition key and issue_id as sort key
                item = {
                    'repo_name': repo,
                    'issue_id': issue_data['id'],
                    'issue_number': issue_data['number'],
                    **issue_data
                }
                
                batch.put_item(Item=item)
                cached_count += 1
                
        logger.info(f"Successfully cached {cached_count} issues for {repo}")
        
    except Exception as e:
        logger.error(f"Failed to cache issues in DynamoDB: {str(e)}")
        raise
    
    return cached_count


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for POST /scan endpoint.
    
    Event format:
    {
        "body": "{\"repo\": \"owner/repo-name\"}"
    }
    
    Returns:
    {
        "statusCode": 200,
        "body": "{\"repo\": \"...\", \"issues_fetched\": 42, \"cached_successfully\": true}"
    }
    """
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        repo = body.get('repo')
        
        if not repo:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required field: repo',
                    'example': '{"repo": "owner/repo-name"}'
                })
            }
        
        logger.info(f"Starting scan for repository: {repo}")
        
        # Get GitHub token
        token = get_github_token()
        
        # Fetch issues from GitHub
        issues = fetch_github_issues(repo, token)
        logger.info(f"Fetched {len(issues)} issues from GitHub")
        
        # Cache issues in DynamoDB
        cached_count = cache_issues(repo, issues)
        
        response = {
            'repo': repo,
            'issues_fetched': len(issues),
            'cached_successfully': True,
            'cached_count': cached_count,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Scan completed successfully for {repo}")
        
        return {
            'statusCode': 200,
            'body': json.dumps(response),
            'headers': {
                'Content-Type': 'application/json'
            }
        }
        
    except ValueError as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': str(e)})
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"GitHub API error: {str(e)}")
        return {
            'statusCode': 502,
            'body': json.dumps({
                'error': 'Failed to fetch issues from GitHub',
                'details': str(e)
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'details': str(e)
            })
        }
