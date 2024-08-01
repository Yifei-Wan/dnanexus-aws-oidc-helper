import json
import boto3
import os
import yaml
import argparse
import logging
from typing import Any, Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Custom constructors for CloudFormation intrinsic functions
def yaml_constructor_getatt(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    """Constructs a dictionary representing the !GetAtt CloudFormation intrinsic function.

    Args:
        loader (yaml.Loader): The YAML loader instance.
        node (yaml.Node): The current YAML node being processed.

    Returns:
        Dict[str, Any]: A dictionary representing the !GetAtt function.
    """
    return {"Fn::GetAtt": loader.construct_scalar(node)}

def yaml_constructor_ref(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    """Constructs a dictionary representing the !Ref CloudFormation intrinsic function.

    Args:
        loader (yaml.Loader): The YAML loader instance.
        node (yaml.Node): The current YAML node being processed.

    Returns:
        Dict[str, Any]: A dictionary representing the !Ref function.
    """
    return {"Ref": loader.construct_scalar(node)}

def yaml_constructor_sub(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    """Constructs a dictionary representing the !Sub CloudFormation intrinsic function.

    Args:
        loader (yaml.Loader): The YAML loader instance.
        node (yaml.Node): The current YAML node being processed.

    Returns:
        Dict[str, Any]: A dictionary representing the !Sub function.
    """
    return {"Fn::Sub": loader.construct_scalar(node)}

def get_user_input() -> Dict[str, Any]:
    """Prompts the user for OIDC provider configuration inputs and returns the collected data.

    Returns:
        Dict[str, Any]: A dictionary containing the user-provided configuration data.
    """
    url = input("Enter the OIDC provider URL: ")
    aud = input("Enter the audience (aud) value")
    project_id = input("Enter the project ID: ")
    launched_by = input("Enter the launched by value: ")
    bucket_name = input("Enter the S3 bucket name: ")
    return {
        "Url": url,
        "ClientIdList": [aud],
        "Aud": aud,
        "ProjectId": project_id,
        "LaunchedBy": launched_by,
        "BucketName": bucket_name
    }

def get_input_from_json(file_path: str) -> Dict[str, Any]:
    """Loads OIDC provider configuration data from a JSON file.

    Args:
        file_path (str): The path to the JSON file.

    Returns:
        Dict[str, Any]: A dictionary containing the loaded configuration data.
    """
    with open(file_path, 'r') as file:
        return json.load(file)

def customize_template(template: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Customizes the CloudFormation template with user-provided data.

    Args:
        template (Dict[str, Any]): The base CloudFormation template.
        data (Dict[str, Any]): The user-provided configuration data.

    Returns:
        Dict[str, Any]: The customized CloudFormation template.
    """
    template['Resources']['MyOIDCProvider']['Properties']['Url'] = data['Url']
    template['Resources']['MyOIDCProvider']['Properties']['ClientIdList'] = data['ClientIdList']
    return template

def load_yaml_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """Loads YAML data from a file.

    Args:
        file_path (str): The path to the YAML file.

    Returns:
        Optional[Dict[str, Any]]: The loaded YAML data as a dictionary, or None if the file does not exist.
    """
    if not os.path.exists(file_path):
        logging.error(f"The specified file does not exist: {file_path}")
        return None
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def replace_policy_placeholders(policy: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Replaces placeholders in the policy with actual values.

    Args:
        policy (Dict[str, Any]): The policy containing placeholders.
        data (Dict[str, Any]): The user-provided configuration data.

    Returns:
        Dict[str, Any]: The policy with placeholders replaced by actual values.
    """
    policy_str = json.dumps(policy)
    policy_str = policy_str.replace("placeholder_aud", data["Aud"])
    policy_str = policy_str.replace("placeholder_project_id", data["ProjectId"])
    policy_str = policy_str.replace("placeholder_launched_by", data["LaunchedBy"])
    policy_str = policy_str.replace("<YOUR_BUCKET_NAME>", data["BucketName"])
    return json.loads(policy_str)

def add_dnanexus_role(template: Dict[str, Any], trust_policy: Dict[str, Any], s3_policy: Dict[str, Any]) -> Dict[str, Any]:
    """Adds the DNANexus role to the CloudFormation template.

    Args:
        template (Dict[str, Any]): The CloudFormation template to be customized.
        trust_policy (Dict[str, Any]): The trust policy to be applied.
        s3_policy (Dict[str, Any]): The S3 policy to be applied.

    Returns:
        Dict[str, Any]: The customized CloudFormation template.
    """
    if not trust_policy or not s3_policy:
        logging.error("Trust policy or S3 policy is missing.")
        raise ValueError("Trust policy or S3 policy is missing.")

    # Replace the Federated placeholder with a reference to the OIDC provider ARN
    trust_policy['Statement'][0]['Principal']['Federated'] = {"Fn::GetAtt": ["MyOIDCProvider", "Arn"]}

    # Update the template with the trust policy and S3 policy
    template['Resources']['DNANexusRole']['Properties']['AssumeRolePolicyDocument'] = trust_policy
    template['Resources']['DNANexusRole']['Properties']['Policies'][0]['PolicyDocument'] = s3_policy

    return template

def save_template_to_file(template: Dict[str, Any], file_path: str) -> None:
    """Saves the customized CloudFormation template to a file.

    Args:
        template (Dict[str, Any]): The customized CloudFormation template.
        file_path (str): The path to the output file.
    """
    with open(file_path, 'w') as file:
        yaml.dump(template, file, default_flow_style=False)

def deploy_cloudformation_stack(template_file: str, stack_name: str, profile: str) -> bool:
    """Deploys the CloudFormation stack using the provided template.

    Args:
        template_file (str): The path to the CloudFormation template file.
        stack_name (str): The name of the CloudFormation stack.
        profile (str): The AWS CLI profile to use.

    Returns:
        bool: True if the stack deployment was initiated successfully, False otherwise.
    """
    logging.info(f"Using AWS profile: {profile}")
    session = boto3.Session(profile_name=profile)
    client = session.client('cloudformation')
    with open(template_file, 'r') as file:
        template_body = file.read()
    
    try:
        response = client.create_stack(
            StackName=stack_name,
            TemplateBody=template_body,
            Capabilities=['CAPABILITY_NAMED_IAM']
        )
        logging.info(f"Stack creation initiated: {response['StackId']}")
    except client.exceptions.ClientError as e:
        logging.error(f"Failed to create stack: {e.response['Error']['Message']}")
        return False
    return True


def main() -> None:
    """Main function to handle argument parsing and orchestrate the workflow."""
    # Register the constructors with PyYAML
    yaml.add_constructor('!GetAtt', yaml_constructor_getatt, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Ref', yaml_constructor_ref, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Sub', yaml_constructor_sub, Loader=yaml.SafeLoader)
    
    parser = argparse.ArgumentParser(description="Create and deploy an AWS OIDC provider using CloudFormation, specifically for DNANexus platform and Nextflow pipeline.")
    parser.add_argument('--json-file', type=str, help="Path to the JSON file (if not provided, prompt will be used)")
    parser.add_argument('--template-file', type=str, default='templates/oidc-template.yaml', help="Path to the base YAML template (default: templates/oidc-template.yaml)")
    parser.add_argument('--profile', type=str, default='default', help="AWS CLI profile to use (default: 'default')")
    parser.add_argument('--stack-name', type=str, default='my-stack', help="Name of the CloudFormation stack (default: 'my-stack')")
    parser.add_argument('--trust-policy-file', type=str, default='templates/trust-policy-template.json', help="Path to the trust policy JSON file (default: 'templates/trust-policy.json')")
    parser.add_argument('--s3-policy-file', type=str, default='templates/s3-policy-template.yaml', help="Path to the S3 policy YAML file (default: 'templates/s3-policy.yaml')")
    parser.add_argument('--rm-yaml', type=bool, default=True, help="Remove the generated YAML file after execution (default: True)")
    parser.add_argument('--dry-run', action='store_true', help="Print the generated YAML template and exit without deploying")

    args = parser.parse_args()

    if args.json_file:
        if not os.path.exists(args.json_file):
            logging.error("The specified JSON file does not exist.")
            raise FileNotFoundError("The specified JSON file does not exist.")
        data = get_input_from_json(args.json_file)
    else:
        data = get_user_input()
    
    template = load_yaml_from_file(args.template_file)
    if template is None:
        raise
    
    trust_policy = load_yaml_from_file(args.trust_policy_file)
    s3_policy = load_yaml_from_file(args.s3_policy_file)

    trust_policy = replace_policy_placeholders(trust_policy, data)
    s3_policy = replace_policy_placeholders(s3_policy, data)

    template = customize_template(template, data)
    template = add_dnanexus_role(template, trust_policy, s3_policy)

    output_file = 'customized_template.yaml'
    save_template_to_file(template, output_file)

    if args.dry_run:
        logging.info("Dry run completed. The generated template is:")
        with open(output_file, 'r') as file:
            print(file.read())
    else:
        success = deploy_cloudformation_stack(output_file, args.stack_name, args.profile)
        if success:
            logging.info("Stack deployment initiated successfully.")
        if args.rm_yaml:
            os.remove(output_file)

if __name__ == "__main__":
    main()
