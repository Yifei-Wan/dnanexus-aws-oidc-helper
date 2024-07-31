import json
import boto3
import os
import yaml
import argparse


# Custom constructors for CloudFormation intrinsic functions
def yaml_constructor_getatt(loader, node):
    return {"Fn::GetAtt": loader.construct_scalar(node)}


def yaml_constructor_ref(loader, node):
    return {"Ref": loader.construct_scalar(node)}


def yaml_constructor_sub(loader, node):
    return {"Fn::Sub": loader.construct_scalar(node)}


def get_user_input():
    url = input("Enter the OIDC provider URL: ")
    client_id = input("Enter the client ID (default: sts.amazonaws.com): ") or 'sts.amazonaws.com'
    #thumbprint = input("Enter the thumbprint of the OIDC provider's certificate: ")
    return {
        "Url": url,
        "ClientIdList": [client_id],
    #    "ThumbprintList": [thumbprint]
    }

def get_input_from_json(file_path):
    with open(file_path, 'r') as file:
        return json.load(file)

def customize_template(template, data):
    template['Resources']['MyOIDCProvider']['Properties']['Url'] = data['Url']
    template['Resources']['MyOIDCProvider']['Properties']['ClientIdList'] = data['ClientIdList']
    #template['Resources']['MyOIDCProvider']['Properties']['ThumbprintList'] = data['ThumbprintList']
    return template

def save_template_to_file(template, file_path):
    with open(file_path, 'w') as file:
        yaml.dump(template, file, default_flow_style=False)

def deploy_cloudformation_stack(template_file, stack_name, profile):
    print(profile)
    session = boto3.Session(profile_name=profile)
    client = session.client('cloudformation')
    with open(template_file, 'r') as file:
        template_body = file.read()
    
    response = client.create_stack(
        StackName=stack_name,
        TemplateBody=template_body,
        Capabilities=['CAPABILITY_NAMED_IAM']
    )
    print(f"Stack creation initiated: {response['StackId']}")

def main():
    # Register the constructors with PyYAML
    yaml.add_constructor('!GetAtt', yaml_constructor_getatt, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Ref', yaml_constructor_ref, Loader=yaml.SafeLoader)
    yaml.add_constructor('!Sub', yaml_constructor_sub, Loader=yaml.SafeLoader)
    parser = argparse.ArgumentParser(description="Create and deploy an AWS OIDC provider using CloudFormation, specifically for DNANexus platform and Nextflow pipeline.")
    parser.add_argument('--json-file', type=str, help="Path to the JSON file (if not provided, prompt will be used)")
    parser.add_argument('--template-file', type=str, default='templates/oidc-template.yaml', help="Path to the base YAML template (default: templates/oidc-template.yaml)")
    parser.add_argument('--profile', type=str, default='default', help="AWS CLI profile to use (default: 'default')")
    parser.add_argument('--stack-name', type=str, required=True, help="Name of the CloudFormation stack")

    args = parser.parse_args()

    if args.json_file:
        if not os.path.exists(args.json_file):
            print("The specified JSON file does not exist.")
            return
        data = get_input_from_json(args.json_file)
    else:
        data = get_user_input()
    
    if not os.path.exists(args.template_file):
        print("The specified YAML template file does not exist.")
        return
    
    with open(args.template_file, 'r') as file:
        template = yaml.safe_load(file)
    
    customized_template = customize_template(template, data)
    customized_template_file_path = 'customized-oidc-provider-template.yaml'
    save_template_to_file(customized_template, customized_template_file_path)
    deploy_cloudformation_stack(customized_template_file_path, args.stack_name, args.profile)


if __name__ == "__main__":
    main()