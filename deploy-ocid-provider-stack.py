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

def yaml_constructor_getatt(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    """
    Custom YAML constructor for the CloudFormation GetAtt intrinsic function.

    Args:
        loader (yaml.Loader): YAML loader instance.
        node (yaml.Node): YAML node to construct.

    Returns:
        Dict[str, Any]: Dictionary representing the Fn::GetAtt function.
    """
    return {"Fn::GetAtt": loader.construct_scalar(node)}

def yaml_constructor_ref(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    """
    Custom YAML constructor for the CloudFormation Ref intrinsic function.

    Args:
        loader (yaml.Loader): YAML loader instance.
        node (yaml.Node): YAML node to construct.

    Returns:
        Dict[str, Any]: Dictionary representing the Ref function.
    """
    return {"Ref": loader.construct_scalar(node)}

def yaml_constructor_sub(loader: yaml.Loader, node: yaml.Node) -> Dict[str, Any]:
    """
    Custom YAML constructor for the CloudFormation Sub intrinsic function.

    Args:
        loader (yaml.Loader): YAML loader instance.
        node (yaml.Node): YAML node to construct.

    Returns:
        Dict[str, Any]: Dictionary representing the Fn::Sub function.
    """
    return {"Fn::Sub": loader.construct_scalar(node)}

def get_user_input() -> Dict[str, Any]:
    """
    Prompt the user for OIDC provider URL and client ID.

    Returns:
        Dict[str, Any]: Dictionary containing the user-provided URL and ClientIdList.
    """
    url = input("Enter the OIDC provider URL: ")
    client_id = input("Enter the client ID: ")
    return {
        "Url": url,
        "ClientIdList": [client_id]
    }

def get_input_from_json(file_path: str) -> Dict[str, Any]:
    """
    Load input data from a JSON file.

    Args:
        file_path (str): Path to the JSON file.

    Returns:
        Dict[str, Any]: Dictionary containing data loaded from the JSON file.
    """
    with open(file_path, 'r') as file:
        return json.load(file)

def customize_template(template: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Customize the CloudFormation template with the provided data.

    Args:
        template (Dict[str, Any]): The original CloudFormation template.
        data (Dict[str, Any]): Data to customize the template with.

    Returns:
        Dict[str, Any]: The customized CloudFormation template.
    """
    template['Resources']['OIDCProvider']['Properties']['Url'] = data['Url']
    template['Resources']['OIDCProvider']['Properties']['ClientIdList'] = data['ClientIdList']
    return template

def load_yaml_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load a YAML file from the specified path.

    Args:
        file_path (str): Path to the YAML file.

    Returns:
        Optional[Dict[str, Any]]: Dictionary representing the YAML content, or None if the file does not exist.
    """
    if not os.path.exists(file_path):
        logging.error(f"The specified file does not exist: {file_path}")
        return None
    with open(file_path, 'r') as file:
        return yaml.safe_load(file)

def save_template_to_file(template: Dict[str, Any], file_path: str) -> None:
    """
    Save the given CloudFormation template to a file.

    Args:
        template (Dict[str, Any]): The CloudFormation template to save.
        file_path (str): Path to save the YAML file.
    """
    with open(file_path, 'w') as file:
        yaml.dump(template, file, default_flow_style=False)

def get_stack_status(client: Any, stack_name: str) -> str:
    """
    Get the current status of the specified CloudFormation stack.

    Args:
        client (Any): Boto3 CloudFormation client.
        stack_name (str): Name of the CloudFormation stack.

    Returns:
        str: Current status of the CloudFormation stack.
    """
    response = client.describe_stacks(StackName=stack_name)
    return response['Stacks'][0]['StackStatus']

def get_stack_events(client: Any, stack_name: str, start_time: datetime) -> None:
    """
    Retrieve and log events for the specified CloudFormation stack.

    Args:
        client (Any): Boto3 CloudFormation client.
        stack_name (str): Name of the CloudFormation stack.
        start_time (datetime): Start time to filter events.
    """
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
    """
    Deploy a CloudFormation stack using the provided template.

    Args:
        template_file (str): Path to the CloudFormation template file.
        stack_name (str): Name of the CloudFormation stack.
        profile (str): AWS CLI profile to use.
        update_stack (bool): Whether to update the stack if it already exists.

    Returns:
        bool: True if the stack deployment succeeded, False otherwise.
    """
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
    """
    Main function to create and deploy an AWS OIDC provider using CloudFormation.
    """
    yaml.add_constructor('!GetAtt', yaml_constructor_getatt, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Ref', yaml_constructor_ref, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Sub', yaml_constructor_sub, Loader=yaml.SafeLoader)
    
    parser = argparse.ArgumentParser(description="Create and deploy an AWS OIDC provider using CloudFormation.")
    parser.add_argument('--json-file', type=str, help="Path to the JSON file for customized configuration (if not provided, prompt will be used)")
    parser.add_argument('--template-file', type=str, default='templates/oidc-template.yaml', help="Path to the base YAML template (default: templates/oidc-template.yaml)")
    parser.add_argument('--profile', type=str, default='default', help="AWS CLI profile to use (default: 'default')")
    parser.add_argument('--stack-name', type=str, default='my-stack', help="Name of the CloudFormation stack (default: 'my-stack')")
    parser.add_argument('--rm-yaml', type=bool, default=True, help="Remove the generated YAML file after execution (default: True)")
    parser.add_argument('--dry-run', action='store_true', help="Print the generated YAML template and exit without deploying")
    parser.add_argument('--update-stack', action='store_true', help="Update the stack if it already exists (default: False)")

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
        raise FileNotFoundError("The specified YAML template file does not exist.")
    
    template = customize_template(template, data)

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
