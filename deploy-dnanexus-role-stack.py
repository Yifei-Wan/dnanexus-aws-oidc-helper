import json
import boto3
import os
import yaml
import argparse
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Custom constructors for CloudFormation intrinsic functions
def yaml_constructor_getatt(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    return {"Fn::GetAtt": loader.construct_scalar(node)}

def yaml_constructor_ref(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    return {"Ref": loader.construct_scalar(node)}

def yaml_constructor_sub(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    return {"Fn::Sub": loader.construct_scalar(node)}

def get_user_input() -> Dict[str, Any]:
    project_id = input("Enter the project ID: ")
    launched_by = input("Enter the launched by value: ")
    bucket_name = input("Enter the S3 bucket name: ")
    return {
        "ProjectId": project_id,
        "LaunchedBy": launched_by,
        "BucketName": bucket_name
    }

def get_input_from_json(file_path: str) -> Dict[str, Any]:
    with open(file_path, 'r') as file:
        return json.load(file)

def fetch_aud_from_oidc(oidc_arn: str, profile: str) -> str:
    """Fetches the audience (aud) from the existing OIDC provider.

    Args:
        oidc_arn (str): The OIDC provider ARN.
        profile (str): The AWS CLI profile to use.

    Returns:
        str: The audience (aud) value.
    """
    session = boto3.Session(profile_name=profile)
    client = session.client('iam')
    response = client.get_open_id_connect_provider(OpenIDConnectProviderArn=oidc_arn)
    return response['ClientIDList'][0]

def customize_template(template: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    return template

def load_yaml_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(file_path):
        logging.error(f"The specified file does not exist: {file_path}")
        return None
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def replace_policy_placeholders(policy: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    policy_str = json.dumps(policy)
    policy_str = policy_str.replace("placeholder_aud", data["Aud"])
    policy_str = policy_str.replace("placeholder_project_id", data["ProjectId"])
    policy_str = policy_str.replace("placeholder_launched_by", data["LaunchedBy"])
    policy_str = policy_str.replace("<YOUR_BUCKET_NAME>", data["BucketName"])
    return json.loads(policy_str)

def add_dnanexus_role(template: Dict[str, Any], trust_policy: Dict[str, Any], s3_policy: Dict[str, Any], oidc_arn: str) -> Dict[str, Any]:
    if not trust_policy or not s3_policy:
        logging.error("Trust policy or S3 policy is missing.")
        raise ValueError("Trust policy or S3 policy is missing.")

    trust_policy['Statement'][0]['Principal']['Federated'] = oidc_arn

    template['Resources']['DNANexusRole']['Properties']['AssumeRolePolicyDocument'] = trust_policy
    template['Resources']['DNANexusRole']['Properties']['Policies'][0]['PolicyDocument'] = s3_policy

    return template

def assign_resource_names(template: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    template['Resources']['DNANexusRole']['Properties']['RoleName'] = f"DNANexusRole-{data['ProjectId']}"
    template['Resources']['DNANexusRole']['Properties']['Policies'][0]['PolicyName'] = f"DNANexusPolicy-{data['ProjectId']}-{data['BucketName']}"
    return template

def save_template_to_file(template: Dict[str, Any], file_path: str) -> None:
    with open(file_path, 'w') as file:
        yaml.dump(template, file, default_flow_style=False)

def get_stack_status(client, stack_name: str) -> str:
    response = client.describe_stacks(StackName=stack_name)
    return response['Stacks'][0]['StackStatus']

def get_stack_events(client, stack_name: str, start_time: datetime) -> None:
    response = client.describe_stack_events(StackName=stack_name)
    for event in response['StackEvents']:
        event_time = event['Timestamp'].replace(tzinfo=timezone.utc)
        if event_time >= start_time:
            message = f"{event['Timestamp']} - {event['ResourceStatus']} - {event['ResourceType']} - {event['LogicalResourceId']} - {event.get('ResourceStatusReason', '')}"
            if event['ResourceStatus'] in ['CREATE_FAILED', 'UPDATE_ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS'] or 'already exists' in event.get('ResourceStatusReason', ''):
                logging.error(message)
            else:
                logging.info(message)

def deploy_cloudformation_stack(template_file: str, stack_name: str, profile: str, update_stack: bool) -> bool:
    logging.info(f"Using AWS profile: {profile}")
    session = boto3.Session(profile_name=profile)
    client = session.client('cloudformation')
    with open(template_file, 'r') as file:
        template_body = file.read()
    
    start_time = datetime.now(timezone.utc)

    try:
        response = client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Capabilities=['CAPABILITY_NAMED_IAM']
        )
        logging.info(f"Stack creation initiated: {response['StackId']}")
    except client.exceptions.ClientError as e:
        if 'AlreadyExistsException' in str(e):
            if update_stack:
                logging.warning(f"Stack {stack_name} already exists. Updating stack.")
                try:
                    response = client.update_stack(
                        StackName=stack_name,
                        TemplateBody=template_body,
                        Capabilities=['CAPABILITY_NAMED_IAM']
                    )
                    logging.info(f"Stack update initiated: {response['StackId']}")
                except client.exceptions.ClientError as update_e:
                    logging.error(f"Failed to update stack: {update_e.response['Error']['Message']}")
                    get_stack_events(client, stack_name, start_time)
                    return False
            else:
                logging.error(f"Stack {stack_name} already exists. Use --update-stack to update the existing stack.")
                return False
        else:
            logging.error(f"Failed to create stack: {e.response['Error']['Message']}")
            get_stack_events(client, stack_name, start_time)
            return False

    while True:
        stack_status = get_stack_status(client, stack_name)
        logging.info(f"Current stack status: {stack_status}")
        if stack_status.endswith('_COMPLETE'):
            logging.info(f"Stack operation completed with status: {stack_status}")
            break
        elif stack_status in ['CREATE_FAILED', 'UPDATE_ROLLBACK_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS']:
            logging.error(f"Stack operation failed with status: {stack_status}")
            get_stack_events(client, stack_name, start_time)
            return False
        time.sleep(5)

    return True

def main() -> None:
    yaml.add_constructor('!GetAtt', yaml_constructor_getatt, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Ref', yaml_constructor_ref, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Sub', yaml_constructor_sub, Loader=yaml.SafeLoader)
    
    parser = argparse.ArgumentParser(description="Create and deploy an AWS OIDC provider using CloudFormation, specifically for DNANexus platform and Nextflow pipeline.")
    parser.add_argument('--json-file', type=str, help="Path to the JSON file for customized configuration (if not provided, prompt will be used)")
    parser.add_argument('--template-file', type=str, default='templates/iam-role-template.yaml', help="Path to the base YAML template (default: templates/oidc-template.yaml)")
    parser.add_argument('--profile', type=str, default='default', help="AWS CLI profile to use (default: 'default')")
    parser.add_argument('--stack-name', type=str, default='my-stack', help="Name of the CloudFormation stack (default: 'my-stack')")
    parser.add_argument('--trust-policy-file', type=str, default='templates/trust-policy-template.json', help="Path to the trust policy JSON file (default: 'templates/trust-policy.json')")
    parser.add_argument('--s3-policy-file', type=str, default='templates/s3-policy-template.yaml', help="Path to the S3 policy YAML file (default: 'templates/s3-policy.yaml')")
    parser.add_argument('--rm-yaml', type=bool, default=True, help="Remove the generated YAML file after execution (default: True)")
    parser.add_argument('--dry-run', action='store_true', help="Print the generated YAML template and exit without deploying")
    parser.add_argument('--update-stack', action='store_true', help="Update the stack if it already exists (default: False)")
    parser.add_argument('--oidc-arn', type=str, required=True, help="OIDC provider ARN")

    args = parser.parse_args()

    if args.json_file:
        if not os.path.exists(args.json_file):
            logging.error("The specified JSON file does not exist.")
            raise FileNotFoundError("The specified JSON file does not exist.")
        data = get_input_from_json(args.json_file)
    else:
        data = get_user_input()

    data['Aud'] = fetch_aud_from_oidc(args.oidc_arn, args.profile)
    
    template = load_yaml_from_file(args.template_file)
    if template is None:
        raise
    
    trust_policy = load_yaml_from_file(args.trust_policy_file)
    s3_policy = load_yaml_from_file(args.s3_policy_file)

    trust_policy = replace_policy_placeholders(trust_policy, data)
    s3_policy = replace_policy_placeholders(s3_policy, data)

    template = customize_template(template, data)
    template = add_dnanexus_role(template, trust_policy, s3_policy, args.oidc_arn)
    template = assign_resource_names(template, data)

    output_file = 'customized_template.yaml'
    save_template_to_file(template, output_file)

    if args.dry_run:
        logging.info("Dry run completed. The generated template is:")
        with open(output_file, 'r') as file:
            print(file.read())
    else:
        success = deploy_cloudformation_stack(output_file, args.stack_name, args.profile, args.update_stack)
        if success:
            logging.info("Stack deployment initiated successfully.")
        if args.rm_yaml:
            os.remove(output_file)

if __name__ == "__main__":
    main()