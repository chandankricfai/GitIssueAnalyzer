"""
Analyze Lambda Function - Analyze cached issues using LLM

This Lambda function handles the POST /analyze endpoint.
It retrieves cached issues from DynamoDB and sends them to an LLM for analysis.
"""

import json
import boto3
import requests
import os
from datetime import datetime
from typing import Dict, Any, List, Tuple
import logging

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Initialize logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'github-issues')
SECRETS_NAME = os.environ.get('SECRETS_NAME', 'llm-api-key')
LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai')
LLM_MODEL = os.environ.get('LLM_MODEL', 'gpt-3.5-turbo')
MAX_CONTEXT_SIZE = int(os.environ.get('MAX_CONTEXT_SIZE', '4000'))

# LLM API endpoints
LLM_ENDPOINTS = {
    'openai': 'https://api.openai.com/v1/chat/completions',
    'anthropic': 'https://api.anthropic.com/v1/messages'
}


def get_llm_api_key() -> str:
    """
    Retrieve LLM API key from AWS Secrets Manager.
    
    Returns:
        str: LLM API key
        
    Raises:
        Exception: If key retrieval fails
    """
    try:
        response = secrets_client.get_secret_value(SecretId=SECRETS_NAME)
        if 'SecretString' in response:
            secret = json.loads(response['SecretString'])
            return secret.get('api_key') or secret.get('llm_api_key')
        else:
            return response['SecretBinary']
    except Exception as e:
        logger.error(f"Failed to retrieve LLM API key: {str(e)}")
        raise


def retrieve_cached_issues(repo: str) -> List[Dict[str, Any]]:
    """
    Retrieve cached issues from DynamoDB for a given repository.
    
    Args:
        repo: Repository name in format "owner/repo-name"
        
    Returns:
        List of cached issue dictionaries
        
    Raises:
        Exception: If DynamoDB query fails
    """
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    
    try:
        response = table.query(
            KeyConditionExpression='repo_name = :repo',
            ExpressionAttributeValues={
                ':repo': repo
            },
            Limit=1000  # Adjust based on needs
        )
        
        issues = response.get('Items', [])
        logger.info(f"Retrieved {len(issues)} cached issues for {repo}")
        
        return issues
        
    except Exception as e:
        logger.error(f"Failed to retrieve issues from DynamoDB: {str(e)}")
        raise


def format_issues_for_llm(issues: List[Dict[str, Any]]) -> str:
    """
    Format issues into a string suitable for LLM processing.
    
    Args:
        issues: List of issue dictionaries
        
    Returns:
        Formatted string representation of issues
    """
    if not issues:
        return "No issues found."
    
    formatted = "GitHub Issues:\n\n"
    
    for issue in issues:
        formatted += f"Issue #{issue.get('issue_number', issue.get('id'))}:\n"
        formatted += f"Title: {issue.get('title', 'N/A')}\n"
        formatted += f"Created: {issue.get('created_at', 'N/A')}\n"
        formatted += f"URL: {issue.get('html_url', 'N/A')}\n"
        
        body = issue.get('body', '')
        if body:
            # Truncate body if too long
            body = body[:500] + "..." if len(body) > 500 else body
            formatted += f"Description: {body}\n"
        
        labels = issue.get('labels', [])
        if labels:
            formatted += f"Labels: {', '.join(labels)}\n"
        
        formatted += "\n"
    
    return formatted


def chunk_issues(issues: List[Dict[str, Any]], max_tokens: int = 3000) -> List[List[Dict[str, Any]]]:
    """
    Split issues into chunks to respect context size limits.
    
    Args:
        issues: List of issue dictionaries
        max_tokens: Maximum tokens per chunk (approximate)
        
    Returns:
        List of issue chunks
    """
    chunks = []
    current_chunk = []
    current_size = 0
    
    # Rough estimate: 1 issue ≈ 200 tokens
    tokens_per_issue = 200
    max_issues_per_chunk = max(1, max_tokens // tokens_per_issue)
    
    for issue in issues:
        if len(current_chunk) >= max_issues_per_chunk:
            chunks.append(current_chunk)
            current_chunk = []
        
        current_chunk.append(issue)
    
    if current_chunk:
        chunks.append(current_chunk)
    
    logger.info(f"Split {len(issues)} issues into {len(chunks)} chunks")
    return chunks


def call_openai_api(api_key: str, prompt: str, issues_text: str) -> str:
    """
    Call OpenAI API for issue analysis.
    
    Args:
        api_key: OpenAI API key
        prompt: User's analysis prompt
        issues_text: Formatted issues text
        
    Returns:
        Analysis response from OpenAI
        
    Raises:
        requests.RequestException: If API call fails
    """
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    # Construct the message
    system_message = "You are a helpful assistant that analyzes GitHub issues and provides insights."
    user_message = f"{prompt}\n\nHere are the issues to analyze:\n\n{issues_text}"
    
    payload = {
        'model': LLM_MODEL,
        'messages': [
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': user_message}
        ],
        'temperature': 0.7,
        'max_tokens': 2000
    }
    
    try:
        response = requests.post(
            LLM_ENDPOINTS['openai'],
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        analysis = result['choices'][0]['message']['content']
        
        logger.info("Successfully received analysis from OpenAI")
        return analysis
        
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenAI API error: {str(e)}")
        raise


def call_anthropic_api(api_key: str, prompt: str, issues_text: str) -> str:
    """
    Call Anthropic API for issue analysis.
    
    Args:
        api_key: Anthropic API key
        prompt: User's analysis prompt
        issues_text: Formatted issues text
        
    Returns:
        Analysis response from Anthropic
        
    Raises:
        requests.RequestException: If API call fails
    """
    headers = {
        'x-api-key': api_key,
        'anthropic-version': '2023-06-01',
        'content-type': 'application/json'
    }
    
    user_message = f"{prompt}\n\nHere are the issues to analyze:\n\n{issues_text}"
    
    payload = {
        'model': 'claude-3-sonnet-20240229',
        'max_tokens': 2000,
        'messages': [
            {'role': 'user', 'content': user_message}
        ]
    }
    
    try:
        response = requests.post(
            LLM_ENDPOINTS['anthropic'],
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        analysis = result['content'][0]['text']
        
        logger.info("Successfully received analysis from Anthropic")
        return analysis
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Anthropic API error: {str(e)}")
        raise


def analyze_issues(repo: str, prompt: str, api_key: str) -> str:
    """
    Analyze cached issues using LLM.
    
    Args:
        repo: Repository name
        prompt: User's analysis prompt
        api_key: LLM API key
        
    Returns:
        Analysis text from LLM
        
    Raises:
        Exception: If analysis fails
    """
    # Retrieve cached issues
    issues = retrieve_cached_issues(repo)
    
    if not issues:
        return f"No cached issues found for repository '{repo}'. Please run /scan endpoint first."
    
    logger.info(f"Analyzing {len(issues)} issues for {repo}")
    
    # Chunk issues if necessary
    chunks = chunk_issues(issues, MAX_CONTEXT_SIZE)
    
    # Analyze each chunk and combine results
    all_analyses = []
    
    for chunk_num, chunk in enumerate(chunks, 1):
        logger.info(f"Analyzing chunk {chunk_num}/{len(chunks)}")
        
        # Format issues for LLM
        issues_text = format_issues_for_llm(chunk)
        
        # Call appropriate LLM API
        if LLM_PROVIDER.lower() == 'openai':
            analysis = call_openai_api(api_key, prompt, issues_text)
        elif LLM_PROVIDER.lower() == 'anthropic':
            analysis = call_anthropic_api(api_key, prompt, issues_text)
        else:
            raise ValueError(f"Unsupported LLM provider: {LLM_PROVIDER}")
        
        all_analyses.append(analysis)
    
    # Combine analyses if multiple chunks
    if len(all_analyses) > 1:
        combined_prompt = "Summarize and combine the following analyses into a single coherent response:\n\n"
        combined_prompt += "\n\n---\n\n".join(all_analyses)
        
        logger.info("Combining analyses from multiple chunks")
        
        if LLM_PROVIDER.lower() == 'openai':
            final_analysis = call_openai_api(api_key, combined_prompt, "")
        else:
            final_analysis = call_anthropic_api(api_key, combined_prompt, "")
        
        return final_analysis
    else:
        return all_analyses[0]


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for POST /analyze endpoint.
    
    Event format:
    {
        "body": "{\"repo\": \"owner/repo-name\", \"prompt\": \"Analyze these issues...\"}"
    }
    
    Returns:
    {
        "statusCode": 200,
        "body": "{\"analysis\": \"...\"}"
    }
    """
    try:
        # Parse request body
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})
        
        repo = body.get('repo')
        prompt = body.get('prompt')
        
        if not repo or not prompt:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Missing required fields: repo and prompt',
                    'example': {
                        'repo': 'owner/repo-name',
                        'prompt': 'Find themes across recent issues...'
                    }
                })
            }
        
        logger.info(f"Starting analysis for repository: {repo}")
        
        # Get LLM API key
        api_key = get_llm_api_key()
        
        # Analyze issues
        analysis = analyze_issues(repo, prompt, api_key)
        
        response = {
            'repo': repo,
            'analysis': analysis,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        logger.info(f"Analysis completed successfully for {repo}")
        
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
        logger.error(f"LLM API error: {str(e)}")
        return {
            'statusCode': 502,
            'body': json.dumps({
                'error': 'Failed to call LLM API',
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
