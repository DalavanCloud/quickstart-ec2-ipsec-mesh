
![Overview](/docs/pics/Tweet_image.png)

# Opportunistic IPSec Mesh (overlay network) for AWS EC2

An opportunistic IPSec mesh builds dynamically secure Internet Protocol Security (IPSec) tunnels between Amazon Elastic Compute Cloud (EC2) instances using libreswan.

## Solution benefits and deliverables
Configuration of site-to-site IPSec between multiple hosts is an error-prone and intensive task. If you need to protect N EC2 instances, then you need full mesh of N x (N-1) IPSec tunnels. You must manually propagate every IP change to all instances, configure credentials, configuration changes, integrate monitoring and metrics into the operation. The efforts to keep the full-mesh parameters in sync are enormous.

The underlying IPSec network will protect all application communication between the network segments you’ve defined. You can use this solution in scenarios where legacy application protocols don’t protect data in-transit—for example, if you’re using File Transfer Protocol (FTP), Hypertext Transfer Protocol (HTTP), Lightweight Directory Access Protocol (LDAP), Trivial File Transfer Protocol (TFTP), Simple Network Management Protocol (SNMP), or Java Database Connectivity (JDBC) protocol.

Solution delivers the automatic setup with the following benefits: 

- IPSec configuration upon EC2 launch, using AWS Systems Manager on the existing EC2 tag with the name IPSec and value todo. 
   - Installation of libreswan and AWS SDK for Python.
   - Configuration of IPSec, including interfaces and subnet classification.
- Generation of instance certificates valid for 30 days, via a dedicated private certificate authority (CA) that uses a serverless AWS Lambda function.
   - Secrets that are generated and encrypted by AWS Key Management Service (KMS) and controlled by AWS Identity and Access Management (IAM) resource policies.
   - Certificates with RSA 4096-bit keys and SHA256 digest. Private keys are AES256 encrypted with 128-bit secrets.  
- Weekly re-enrollment of certificates (every 7 days) using a Lambda function and a scheduled Amazon CloudWatch Event.
- IPSec Monitoring metrics in CloudWatch for each EC2 instance. These metrics show:
   - Active IPSec sessions
   - Internet Key Exchange (IKE) and Encapsulating Security Payload (ESP) errors
   - IPSec session shunts
- Alarms for failures via CloudWatch and Amazon Simple Notification Service (Amazon SNS).
- An initial generation of a CA root key if needed, including IAM Policies and two customer master keys (CMKs) that will protect the CA key and instance key.

### Out of scope: 
This solution does not deliver IPSec protection between EC2 instances and hosts that are on-premises, or between EC2 instances and managed AWS components, like Elastic Load Balancing, Amazon Relational Database Service, or Amazon Kinesis. 
Your EC2 instances must have general IP connectivity that allows NACLs and Security Groups. This solution cannot deliver extra connectivity like VPC peering or Transit VPC can.

## Prerequisites 		

You need the following resources to deploy the solution:
 
- AWS Systems Manager on EC2. You can install it during the EC2 setup with the user data command, which I explain below. Amazon Linux 2 already includes the agent and you do not need to install it.
- Linux RedHat, Amazon Linux 2, or CentOS, all of which already support libreswan minimum v3.20.  For Ubuntu, you need to compile the libreswan package (see https://github.com/libreswan/libreswan) and adapt the script to use APT packet manager instead of Yum. In the next steps, I do not consider Ubuntu.
- During the EC2 setup, Python, pip, jq, SDK for Python, and curl must be installed. You can pre-install them, or the solution will install them using Yum Package Manager. You’ll also need internet access on the EC2, typically via an AWS network address translation (NAT) gateway
- If you are not using AWS QuickSolution, you need a trusted Unix/Linux/MacOS machine with SDK for Python and OpenSSL as on the majority Unix distribution. You also need AWS Admin rights in your account (including API access) during the installation.

## Network configuration adjustment 

The provided configuration matched the default AWS VPC setting. If you want to use with your custom VPN than you will need to adapt the configuration files.

Download the repo
- Edit the following files according to your network setup: 
  - **config/private** should contain all networks with mandatory IPSec protection, such as EC2s which should only be communicated with via IPSec. All of these hosts must have IPSec installed.
  - **config/clear** should contain any networks WITHOUT IPSec protection. For example, these might include DNS Server, LoadBalancer, or Managed DB.
  - **config/clear-or-private** should contain networks with optional IPSec protection. These networks will start clear and attempt to add IPSec.
  - **config/private-or-clear** should also contain networks with optional IPSec protection. However, these networks will start with IPSec and fail back to clear.

## Installation using CloudFormation 

- Click the link below to launch the setup using CloudFormation  
  [![Launch Stack](https://s3.amazonaws.com/cloudformation-examples/cloudformation-launch-stack.png)](https://console.aws.amazon.com/cloudformation/home?#/stacks/new?stackName=EC2-IPSec-Mesh&templateURL=https://aws-quickstart.s3.amazonaws.com/quickstart-ec2-ipsec-mesh/templates/ipsec-setup.yaml)


## Installation using aws_setup.py script

On a trusted Unix/Linux/MacOS machine that has Admin access to AWS and AWS SDK for Python already installed, complete the following steps:

- Execute `./aws_setup.py` and carefully set and verify the parameters. User `-h` to view help. If you do not provide customized options, default values will be generated. The parameters are:
  - Region to install the solution (default: your AWS Command Line Interface region).
  - Buckets for sources, published hosts certificates and CA storage. (Default: random values that follow the pattern ipsec-{hostcerts|cacrypto|sources}-{stackname} will be generated.) 
  - Reuse of already existing CA? (default: no) 
  - Leave encrypted backup copy of the CA key? The password will be printed to stdout (default: no) 
  - Cloud formation stackname (default: ipsec-{random string}). 
  - vpc-id if you want to restrict the provisioning of IPSec to certain vpc-id (default: any)

A sample of the execution can be found at the end of document 
   
## EC2 Instance launch
The tag name **IPSec** with value **todo** controls when IPSec will be configured on the EC2 instance. If the configuration is successful, then the tag value changes to value enabled.

The following steps assume that you’re using RedHat, Amazon Linux 2 or CentOS. 

Note: Steps or details that I don’t explicitly mention can be set to default (or according to your needs).

1. Select an AMI that supports libreswan, like RedHat, Amazon Linux 2 or CentOS. 

2. Select the IAM Role already configured by the solution with the pattern Ec2IPsec-{stackname}. 

Next you need to install SSM agent. You don’t need the following step for Amazon Linux 2, since SSM is preinstalled.
 
Select under Advances setting user data and active SSM Agent by providing to following

2.1 For RedHat and CentOS, the installation is the following string:
``` 
#!/bin/bash
sudo yum install -y https://s3.amazonaws.com/ec2-downloads-windows/SSMAgent/latest/linux_amd64/amazon-ssm-agent.rpm
sudo systemctl start amazon-ssm-agent
```

3. Set the tag name to **IPSec** with the value **todo**. This is the selector to install and maintain IPSec. 

4. On the Configuration page for the security group, allow ESP (Protocol 50) and IKE (UDP 500) for your network, like 172.31.0.0/16
 
After 1-2 minutes, the instance tag **IPSec** will change to **enabled**, meaning the instance is successfully set up. The installation of IPSec and certificate enrolment  is triggered via CloudWatch events.

Every 7 days, CloudWatch will rotate the certificates without stopping internet traffic.

## Solution architecture 

![index](/docs/pics/OverviewDiagram.png)

 
The following steps are executed automatically in background by the solution and can be summarized as:

1. An EC2 launch triggers a CloudWatch event, which launches an IPSecSetup Lambda function.
2. The IPSecSetup Lambda issues a certificate calling a GenerateCertificate Lambda.
3. The GenerateCertificate Lambda downloads the encrypted CA certificate and key. 
4. The GenerateCertificate Lambda decrypts the CA key with a Customer Master Key (CMK).
5. The GenerateCertificate Lambda issues a host certificate to the EC2 instance. It encrypts the host certificate and key with a KMS generated random secret in PKCS12 structure. The secret is envelope encrypted with a dedicated Customer Master Key (CMK)
6. The GenerateCertificate Lambda publishes the issued certificates to your dedicated bucket for documentation. 
7. The IPSec Lambda function calls and runs the installation via SSM. 
8. The installation downloads the configuration and installs python, aws-sdk, libreswan, and curl if needed. 
9. The EC2 instance decrypts the host key with the dedicated CMK and installs it in the IPSec database.
10. Every seven days, a scheduled event triggers reenrollment of the certificates via the Reenrollcertificates Lambda 
11. The Reenrollcertificates Lambda triggers the IPSecSetup Lambda (call event type: execution). The IPSecSetup Lambda will renew the certificate only, leaving the rest of the configuration untouched.


## Changing your configuration or installing it on already running instances

All configuration exists in the source bucket (default: ipsec-source prefix), in files for libreswan standard. If you need to change the configuration:

- Review and update the following files 
  - oe-conf - the configuration for libreswan 
  - clear, private, private-to-clear and clear-to-ipsec – these should contains your network ranges 
- Change the tag for the ipsec instance to IPSec:todo
- Stop and Start the instance (don't restart). This will retrigger the setup of the instance. 
- Alternately to previous step, if you prefer not to stop and start the instance, you can invoke IPSecSetupLambda with a test JSON event in the following format: 
```
  { "detail" :  
     { "instance-id": “YOUR_INSTANCE_ID" }
  }
```
## Testing the connection on the EC2 instance 
You can log in to the instance and ping one of the hosts in your network. This will trigger the IPSec connation and you should see successful answers
```
$ ping 172.31.1.26

PING 172.31.1.26 (172.31.1.26) 56(84) bytes of data.
64 bytes from 172.31.1.26: icmp_seq=2 ttl=255 time=0.722 ms
64 bytes from 172.31.1.26: icmp_seq=3 ttl=255 time=0.483 ms
```

To see a list of IPSec tunnels you can execute 

`sudo ipsec whack --trafficstatus`

## Security 

The CA key is encrypted using an Advanced Encryption Standard (AES) 256 CBC 128-byte secret and stored in a bucket with server-side encryption (SSE). The secret is envelope-encrypted with a CMK in AWS KMP pattern . Only the certificate-issuing Lambda can decrypt the secret (KMS resource policy). The encrypted secret for the CA key is set in an encrypted environment variable of the certificate-issuing serverless Lambda. 

The IPSec host private key is generated by the certificate-issuing Lambda. The private key and certificate are encrypted with AES 256 CBC (PKCS12) and protected with a 128-byte secret generated by KMS. The secret is envelope-encrypted with User CMK. Only the EC2 instances with attached IPSec IAM policy can decrypt the secret and private key. 

The issuing of the certificate is a full synchronous call: One request and one corresponding response without any polling or similar sync/callbacks. The host private key is not stored in a database or an S3 bucket.
 
The issued certificates are valid for 30 days and are stored for auditing purposes in a certificates bucket without a private key.


### Alternate subject names and multiple interfaces or secondary IPs
The certificate subject name and AltSubjectName attribute contain the private Domain Name System (DNS) of the EC2 and all private IPs assigned to the instance (interfaces, primary and secondary IPs).

The provided default libreswan configuration covers a single interface. You can adjust the configuration according to libreswan documentation for multiple interfaces, for example, to cover Amazon Elastic Container Service for Kubernetes (Amazon EKS).
 


