# Manual AWS Setup Guide for GitHub Issue Analyzer

This guide provides step-by-step instructions to manually create and configure all the necessary AWS resources for the GitHub Issue Analyzer application using the AWS Management Console and the AWS CLI. This approach is an alternative to using the automated AWS SAM template.

## 1. Prerequisites

Before you start, ensure you have the following:

- An active **AWS Account** with administrative privileges.
- **AWS CLI** installed and configured (`aws configure`).
- The **Lambda function code** (`lambda_scan.py` and `lambda_analyze.py`).
- A **GitHub Personal Access Token** and an **LLM API Key** (OpenAI or Anthropic).

## 2. Create Secrets in AWS Secrets Manager

First, we will securely store the API keys and tokens.

### Using AWS Management Console

1.  Navigate to the **AWS Secrets Manager** console.
2.  Click **Store a new secret**.
3.  Select **Other type of secret**.
4.  Under **Secret key/value**, create a key-value pair. For the GitHub token, use `github_token` as the key and your token as the value.
5.  Click **Next**.
6.  For **Secret name**, enter `github-token` and click **Next**.
7.  Configure rotation if desired (optional) and click **Next**.
8.  Review and click **Store**.
9.  Repeat the process for your LLM API key, using the secret name `llm-api-key` and the key `api_key`.

### Using AWS CLI

```bash
# Create GitHub Token Secret
aws secretsmanager create-secret --name github-token --secret-string '{"github_token":"YOUR_GITHUB_TOKEN"}'

# Create LLM API Key Secret
aws secretsmanager create-secret --name llm-api-key --secret-string '{"api_key":"YOUR_LLM_API_KEY"}'
```

## 3. Create the DynamoDB Table

This table will cache the GitHub issues.

### Using AWS Management Console

1.  Navigate to the **Amazon DynamoDB** console.
2.  Click **Create table**.
3.  For **Table name**, enter `github-issues`.
4.  For **Partition key**, enter `repo_name` and select `String` as the type.
5.  Check the **Add sort key** box. For **Sort key**, enter `issue_id` and select `Number` as the type.
6.  Under **Table settings**, select **On-demand** for the capacity mode.
7.  Click **Create table**.

### Using AWS CLI

```bash
aws dynamodb create-table \
    --table-name github-issues \
    --attribute-definitions \
        AttributeName=repo_name,AttributeType=S \
        AttributeName=issue_id,AttributeType=N \
    --key-schema \
        AttributeName=repo_name,KeyType=HASH \
        AttributeName=issue_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST
```

## 4. Create IAM Roles for Lambda

We need two separate IAM roles, one for each Lambda function, with specific permissions.

### Using AWS Management Console

1.  Navigate to the **IAM** console and go to **Roles**.
2.  Click **Create role**.
3.  For **Trusted entity type**, select **AWS service**. For **Use case**, select **Lambda**. Click **Next**.
4.  On the **Add permissions** page, search for and add the `AWSLambdaBasicExecutionRole` policy. This allows the function to write logs to CloudWatch.
5.  Click **Next**.
6.  For **Role name**, enter `ScanLambdaRole`. Review and click **Create role**.
7.  Now, find the `ScanLambdaRole` in the list and click on it. Under the **Permissions** tab, click **Add permissions** > **Create inline policy**.
8.  Select the **JSON** tab and paste the following policy to grant access to DynamoDB and Secrets Manager:

    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "dynamodb:BatchWriteItem",
                "Resource": "arn:aws:dynamodb:*:*:table/github-issues"
            },
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": "arn:aws:secretsmanager:*:*:secret:github-token*"
            }
        ]
    }
    ```

9.  Click **Review policy**, give it a name (e.g., `ScanLambdaPermissions`), and click **Create policy**.
10. Repeat steps 2-9 to create a second role named `AnalyzeLambdaRole`. Use the same `AWSLambdaBasicExecutionRole` managed policy, but for the inline policy, use the following JSON, which grants read access to DynamoDB and access to the LLM secret:

    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "dynamodb:Query",
                "Resource": "arn:aws:dynamodb:*:*:table/github-issues"
            },
            {
                "Effect": "Allow",
                "Action": "secretsmanager:GetSecretValue",
                "Resource": "arn:aws:secretsmanager:*:*:secret:llm-api-key*"
            }
        ]
    }
    ```

## 5. Create the Lambda Functions

Now, create the two Lambda functions and upload their code.

### Prepare Deployment Packages

For each function, you need to create a `.zip` file containing the Python script and its dependencies. Since our scripts only use standard libraries and `boto3`/`requests` (which are included in the Lambda runtime), you can simply zip the `.py` files.

```bash
zip lambda_scan.zip lambda_scan.py
zip lambda_analyze.zip lambda_analyze.py
```

### Using AWS Management Console

1.  Navigate to the **AWS Lambda** console.
2.  Click **Create function**.
3.  Select **Author from scratch**.
4.  For **Function name**, enter `github-issue-analyzer-scan`.
5.  For **Runtime**, select **Python 3.11**.
6.  For **Architecture**, select **x86_64**.
7.  Expand **Change default execution role**. Select **Use an existing role** and choose `ScanLambdaRole` from the dropdown.
8.  Click **Create function**.
9.  In the **Code source** section, click **Upload from** and select **.zip file**. Upload `lambda_scan.zip`.
10. Go to the **Configuration** tab and select **Environment variables**. Click **Edit**.
11. Add the following environment variables:
    -   `DYNAMODB_TABLE_NAME`: `github-issues`
    -   `SECRETS_NAME`: `github-token`
12. Click **Save**.
13. Repeat steps 2-12 to create the `github-issue-analyzer-analyze` function. Use the `lambda_analyze.zip` package, the `AnalyzeLambdaRole`, and the following environment variables:
    -   `DYNAMODB_TABLE_NAME`: `github-issues`
    -   `SECRETS_NAME`: `llm-api-key`
    -   `LLM_PROVIDER`: `openai` (or `anthropic`)

## 6. Create the API Gateway

Finally, create the REST API to expose the Lambda functions.

### Using AWS Management Console

1.  Navigate to the **Amazon API Gateway** console.
2.  Find the **REST API** box and click **Build**.
3.  For **API name**, enter `GitHub Issue Analyzer API`. For **Endpoint Type**, select **Regional**. Click **Create API**.
4.  In the **Resources** tree, click the **Actions** dropdown and select **Create Resource**. For **Resource Name**, enter `scan`. Click **Create Resource**.
5.  With the `/scan` resource selected, click **Actions** > **Create Method**. Select **POST** from the dropdown and click the checkmark.
6.  On the setup page for the POST method:
    -   **Integration type**: **Lambda Function**
    -   Check **Use Lambda Proxy integration**.
    -   **Lambda Region**: Your current region.
    -   **Lambda Function**: Start typing `github-issue-analyzer-scan` and select it.
    -   Click **Save**. A dialog will appear asking for permission to invoke the Lambda function. Click **OK**.
7.  Repeat steps 4-6 to create a `/analyze` resource with a POST method integrated with the `github-issue-analyzer-analyze` Lambda function.
8.  Now, deploy the API. Click **Actions** > **Deploy API**.
9.  For **Deployment stage**, select **[New Stage]**. For **Stage name**, enter `dev`.
10. Click **Deploy**.
11. You will be taken to the stage editor, where you can find the **Invoke URL**. This is your API's public endpoint.

## 7. Testing the API

Use the **Invoke URL** from the previous step to test your endpoints.

```bash
# Replace with your Invoke URL
INVOKE_URL="https://<your-api-id>.execute-api.<your-region>.amazonaws.com/dev"

# Test the /scan endpoint
curl -X POST $INVOKE_URL/scan -d '{"repo": "owner/repository-name"}'

# Test the /analyze endpoint
curl -X POST $INVOKE_URL/analyze -d '{"repo": "owner/repository-name", "prompt": "Summarize these issues."}'
```

## 8. Manual Cleanup

To avoid ongoing costs, manually delete the resources in the reverse order of creation:

1.  **API Gateway**: Delete the API.
2.  **Lambda Functions**: Delete the `github-issue-analyzer-scan` and `github-issue-analyzer-analyze` functions.
3.  **IAM Roles**: Delete the `ScanLambdaRole` and `AnalyzeLambdaRole`.
4.  **DynamoDB Table**: Delete the `github-issues` table.
5.  **Secrets Manager**: Delete the `github-token` and `llm-api-key` secrets.
6.  **CloudWatch Log Groups**: Delete the log groups associated with the Lambda functions. 
