# GitHub Issue Analyzer - Serverless Lambda Solution

## Problem Statement Summary

Build a service with two endpoints:
1. **POST /scan** - Fetch and cache GitHub issues from a repository
2. **POST /analyze** - Analyze cached issues using LLM with natural-language prompts

## Serverless Architecture Design

This serverless Lambda-based architecture provides a **scalable, cost-effective, and maintainable** solution for the GitHub Issue Analyzer. By leveraging AWS managed services, we eliminate operational overhead while maintaining high performance and reliability.


### Overview

This solution uses **AWS Lambda** as the compute layer with supporting AWS services for a fully serverless, scalable, and cost-effective implementation.

### Architecture Components

#### 1. **API Gateway**
- **Purpose**: Expose REST endpoints (`/scan` and `/analyze`)
- **Benefits**: 
  - Automatic scaling
  - Built-in request validation
  - CORS support
  - Request/response transformation

#### 2. **Lambda Functions**
Two separate Lambda functions for separation of concerns:

**Function 1: Scan Lambda**
- Triggered by POST /scan endpoint
- Fetches issues from GitHub REST API
- Stores issues in DynamoDB
- Returns summary response

**Function 2: Analyze Lambda**
- Triggered by POST /analyze endpoint
- Retrieves cached issues from DynamoDB
- Chunks issues if needed (context size management)
- Calls LLM API (OpenAI, Anthropic, etc.)
- Returns analysis results

#### 3. **DynamoDB**
- **Purpose**: Serverless, scalable NoSQL database for caching issues
- **Advantages over alternatives**:
  - **vs In-memory**: Persists across Lambda invocations and function restarts
  - **vs JSON files**: Better performance, automatic scaling, no file system management
  - **vs SQLite**: Serverless (no server management), pay-per-request pricing, built-in AWS integration
- **Table Structure**:
  ```
  PK: repo_name (String)
  SK: issue_id (Number)
  Attributes: title, body, html_url, created_at, timestamp
  ```

#### 4. **CloudWatch Logs**
- Automatic logging of Lambda execution
- Error tracking and debugging
- Performance monitoring

#### 5. **IAM Roles & Policies**
- Lambda execution role with permissions for:
  - DynamoDB read/write
  - CloudWatch Logs
  - External API calls (GitHub, LLM providers)

#### 6. **Secrets Manager**
- Secure storage for:
  - GitHub API tokens
  - LLM API keys
  - Database credentials

#### 7. **CloudFormation / SAM**
- Infrastructure as Code for deployment
- Reproducible deployments
- Easy teardown and updates

### Data Flow

#### Scan Flow
```
Client Request (POST /scan)
    ↓
API Gateway
    ↓
Scan Lambda
    ↓
GitHub REST API (fetch issues)
    ↓
DynamoDB (cache issues)
    ↓
Response (summary)
```

#### Analyze Flow
```
Client Request (POST /analyze)
    ↓
API Gateway
    ↓
Analyze Lambda
    ↓
DynamoDB (retrieve cached issues)
    ↓
LLM API (OpenAI/Anthropic/etc.)
    ↓
Response (analysis)
```

### Key Features

#### 1. **Scalability**
- Lambda auto-scales based on concurrent requests
- DynamoDB auto-scales with on-demand pricing
- No server management required

#### 2. **Cost Efficiency**
- Pay only for what you use
- Lambda: $0.20 per 1M requests + compute time
- DynamoDB: $1.25 per million write units (on-demand)
- No idle server costs

#### 3. **Reliability**
- Built-in redundancy across availability zones
- Automatic retries for transient failures
- Dead-letter queues for error handling (optional)

#### 4. **Security**
- Secrets Manager for sensitive data
- IAM role-based access control
- VPC support for private resources
- Encryption at rest and in transit

#### 5. **Monitoring & Debugging**
- CloudWatch Logs for all Lambda executions
- X-Ray for distributed tracing
- CloudWatch Alarms for error rates

### Error Handling Strategy

#### Scan Lambda
- **GitHub API errors**: Retry with exponential backoff, return error response
- **DynamoDB errors**: Retry with exponential backoff, return error response
- **Invalid repo format**: Return 400 Bad Request

#### Analyze Lambda
- **Repo not cached**: Return 404 with message "Repository not yet scanned"
- **No issues cached**: Return 200 with empty analysis
- **LLM API errors**: Retry, return error response
- **Context size exceeded**: Implement chunking strategy (process issues in batches)

### Storage Choice: DynamoDB

**Why DynamoDB over alternatives?**

| Aspect | In-Memory | JSON File | SQLite | DynamoDB |
|--------|-----------|-----------|--------|----------|
| Persistence | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| Serverless | ❌ No | ⚠️ Partial | ❌ No | ✅ Yes |
| Scalability | ❌ Limited | ❌ Poor | ⚠️ Limited | ✅ Excellent |
| Performance | ✅ Fast | ❌ Slow | ✅ Good | ✅ Fast |
| AWS Integration | ❌ No | ❌ No | ❌ No | ✅ Native |
| Cost Model | N/A | Storage | N/A | Pay-per-request |

**DynamoDB is optimal for serverless Lambda** because:
1. Fully managed (no database administration)
2. Auto-scales with demand
3. Integrates seamlessly with Lambda
4. Provides fast, consistent performance
5. Cost-effective for variable workloads

### Deployment Strategy

#### Infrastructure as Code (SAM Template)
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Transform: AWS::Serverless-2010-05-13

Resources:
  # API Gateway
  IssueAnalyzerApi:
    Type: AWS::Serverless::Api
    
  # Scan Lambda
  ScanFunction:
    Type: AWS::Serverless::Function
    
  # Analyze Lambda
  AnalyzeFunction:
    Type: AWS::Serverless::Function
    
  # DynamoDB Table
  IssuesTable:
    Type: AWS::DynamoDB::Table
    
  # IAM Roles
  LambdaExecutionRole:
    Type: AWS::IAM::Role
```

#### Deployment Steps
1. Create AWS account and configure CLI
2. Create SAM template
3. Build: `sam build`
4. Deploy: `sam deploy --guided`
5. Test endpoints with curl or Postman

### Configuration & Environment Variables

Lambda environment variables:
- `GITHUB_API_TOKEN`: GitHub personal access token
- `LLM_API_KEY`: LLM provider API key
- `LLM_PROVIDER`: Provider name (openai, anthropic, etc.)
- `DYNAMODB_TABLE_NAME`: Issues table name
- `MAX_CONTEXT_SIZE`: LLM context limit (e.g., 4000 tokens)

### Monitoring & Logging

#### CloudWatch Metrics
- Lambda invocation count
- Lambda duration
- Lambda errors
- DynamoDB read/write capacity

#### CloudWatch Logs
- All Lambda execution logs
- GitHub API call logs
- LLM API call logs
- Error stack traces




