# Automating Amazon Q Business Subscription Management in AWS IAM Identity Center

Customers often want automation to assign users and groups to an Amazon Q Business application. Currently there are no APIs that support this operation.
This solution provides an automation mechanism for the operation using the console APIs.
## Workflow

![Addition of Subscription](user-group-assignment-add.png)

![Deletion of Subscription](user-group-assignment-delete.png)

## Prerequisites
Prepare the Python requests module to create a Lambda layer with the steps below.

1. Save the `requests`  Python module to a directory and zip it.

```
mkdir library
pip install -t library requests
zip -r9 python_requests_layer.zip library
```
2. Upload the Zip file from Step 1 to an S3 bucket.

## Installation

Deploy the CloudFormation template `user-group-subscription-template.yaml` with the S3 bucket having the request zip file as input.

## Cleanup

1. Delete the CloudFormation template.
2. Delete the requets zip file from the S3 bucket.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

