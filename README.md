# dnanexus-aws-oidc-helper
This repository provides a helper script to create and deploy an AWS OIDC (OpenID connect) provider using CloudFormation. The script is tailored for integration with the DNANexus platform and the Nextflow pipeline, streamlining the setup process for seamless cloud-based workflows.

## Prerequisites
- python 3.6+
- Dependencies
```
pip install -r requirements.txt
```
- aws credential
Please ensure your AWS credential file is located at:
```
ls ~/.aws/credentials 
```

## Important Notice
The OIDC provider with ARN `arn:aws:iam::733024369092:oidc-provider/job-oidc.dnanexus.com` has already been created for AWS account `733024369092`. There is no need to redeploy the OIDC provider. Please move on to the next step: *2. Deploy IAM Role Stack* and use the provided OIDC ARN.

## 1. Deploy OIDC Provider Stack

The script `deploy-oidc-provider-stack.py` deploys an OIDC provider using a default CloudFormation template. Customized configurations can be provided by a JSON file or via prompt. You can find the demo JSON file in the `tests` folder. If you want to specify the AWS profile, use `--profile`.

 ```
python deploy-oidc-provider-stack.py --json-file tests/customized-config-demo.json --stack-name dnanexus-oidc-stack

2024-08-01 17:19:45,372 - INFO - Using AWS profile: default
2024-08-01 17:19:45,379 - INFO - Found credentials in shared credentials file: ~/.aws/credentials
2024-08-01 17:19:46,668 - INFO - Stack creation initiated: arn:aws:cloudformation:us-east-1:733024369092:stack/dnanexus-oidc-stack/c720a770-504b-11ef-99f4-0affc5f60061
2024-08-01 17:19:46,722 - INFO - Current stack status: CREATE_IN_PROGRESS
2024-08-01 17:19:51,780 - INFO - Current stack status: CREATE_COMPLETE
2024-08-01 17:19:51,780 - INFO - Stack operation completed with status: CREATE_COMPLETE
2024-08-01 17:19:51,783 - INFO - Stack deployment was successful.
2024-08-01 17:19:51,795 - INFO - Found credentials in shared credentials file: ~/.aws/credentials
>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
2024-08-01 17:19:51,980 - INFO - OIDC Provider ARN: arn:aws:iam::733024369092:oidc-provider/job-oidc.dnanexus.com
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
```

## 2. Deploy IAM role stack
The `deploy-dnanexus-role-stack.py` script deploys the IAM role, the trust policie, and S3 access policies for DNANexus users using a CloudFormation template. Customized configurations can be provided by a JSON file or via prompt. A demo JSON file can be found in the tests folder. To specify the AWS profile, use the --profile option. Please use the OIDC Provider ARN printed by `deploy-oidc-provider-stack.py` for the `--oidc-arn` argument.

```
python deploy-dnanexus-role-stack.py --json-file tests/customized-config-demo.json --stack dnanexus-iam-role-stack --oidc-arn arn:aws:iam::733024369092:oidc-provider/job-oidc.dnanexus.com
2024-08-01 18:21:52,471 - INFO - Found credentials in shared credentials file: ~/.aws/credentials
2024-08-01 18:21:52,941 - INFO - Using AWS profile: default
2024-08-01 18:21:52,949 - INFO - Found credentials in shared credentials file: ~/.aws/credentials
2024-08-01 18:21:53,338 - INFO - Stack creation initiated: arn:aws:cloudformation:us-east-1:733024369092:stack/dnanexus-iam-role-stack/745aaff0-5054-11ef-996d-0affde96e0ab
2024-08-01 18:21:53,394 - INFO - Current stack status: CREATE_IN_PROGRESS
2024-08-01 18:21:58,450 - INFO - Current stack status: CREATE_IN_PROGRESS
2024-08-01 18:22:03,497 - INFO - Current stack status: CREATE_IN_PROGRESS
2024-08-01 18:22:08,553 - INFO - Current stack status: CREATE_IN_PROGRESS
2024-08-01 18:22:13,612 - INFO - Current stack status: CREATE_IN_PROGRESS
2024-08-01 18:22:18,666 - INFO - Current stack status: CREATE_COMPLETE
2024-08-01 18:22:18,666 - INFO - Stack operation completed with status: CREATE_COMPLETE
2024-08-01 18:22:18,668 - INFO - Stack deployment was successful.
2024-08-01 18:22:18,683 - INFO - Found credentials in shared credentials file: ~/.aws/credentials
>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
2024-08-01 18:22:18,907 - INFO - IAM Role ARN: arn:aws:iam::733024369092:role/DNANexusRole-project-GY4VJ5j0PZK3pg02qqFKvK3Q
<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
```

## 3. Optional: Nextflow Configuration
To configure Nextflow, add the following to your `nextflow.config` file. Make sure to update the `iamRoleArnToAssume` value with the role IAM ARN obtained in Step `2.Deploy IAM role stack`.

```
// AWS Config
aws {
    region = 'us-east-1'
}

// DNANexus OIDC
dnanexus {
    jobTokenAudience = 'dfci'
    iamRoleArnToAssume = 'arn:aws:iam::733024369092:role/DNANexusJobRole'
    jobTokenSubjectClaims = 'project_id,launched_by'
}
```