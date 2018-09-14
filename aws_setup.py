#!/usr/bin/python
"""
 Copyright 2016 Amazon.com, Inc. or its affiliates. All Rights Reserved.

 Licensed under the Apache License, Version 2.0 (the "License"). You
 may not use this file except in compliance with the License. A copy of
 the License is located at

     http://aws.amazon.com/apache2.0/

 or in the "license" file accompanying this file. This file is
 distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
 ANY KIND, either express or implied. See the License for the specific
 language governing permissions and limitations under the License.
"""

import boto3, random, string, subprocess, botocore
import os
import base64

conf_source_files = ['config/clear', 'config/private', 'config/clear-or-private', 'config/private-or-clear', 'config/oe-cert.conf',
                     'functions/packages/enroll_cert_lambda_function/enroll_cert_lambda_function.zip', 
                     'functions/packages/generate_certifcate_lambda_function/generate_certifcate_lambda_function.zip',
                     'functions/packages/ipsec_setup_lambda_function/ipsec_setup_lambda_function.zip',
                     'templates/ipsec-setup.yaml',
                     'sources/cron.txt', 'sources/cronIPSecStats.sh', 'sources/setup_ipsec.sh',
                     'README.md', 'aws_setup.py']

code_version = "0.4"

# Create bucket if does not exists
# if the bucket exists the region must match 
def createBucket (s3, region, name):
    try:
        r = s3.get_bucket_location(Bucket=name)
        print("The bucket " + name + " already exists")
        if  r['LocationConstraint']:
            print('Region of bucker ' + name + ' is ' +  r['LocationConstraint'])
            if r['LocationConstraint'] != region :
               raise Exception('Error: The bucket ' + name + ' is in region ' + r['LocationConstraint'] + ' and NOT in ' + region + ' as expected')

    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print('bucket does not exists')
            if region == 'us-east-1': 
                s3.create_bucket(Bucket = name)
            else:
                s3.create_bucket(Bucket = name , CreateBucketConfiguration={'LocationConstraint': region})

            s3.put_bucket_versioning( Bucket = name, VersioningConfiguration={'Status': 'Enabled'})
            s3.put_bucket_encryption( Bucket = name,
                ServerSideEncryptionConfiguration = { 'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]})
            print('Bucket ' + name + ' created')

        if e.response['Error']['Code'] == 'AllAccessDisabled':
           raise Exception('Error: The bucket ' + name + ' exist, but can not be accessed. Are you owner of the bucket? ')

# Uploads sources to S3
def upload_files(region, hostcerts_bucket, sources_bucket):
    #   Create source and config bucket and uplaods config and sources
    s3 = boto3.client('s3', region_name=region)
    createBucket(s3, region, sources_bucket)

    for f in conf_source_files:
        data = open(f, 'rb')
        s3.put_object(Bucket=sources_bucket, Key='ipsec/' + f , Body=data)
        print('File ' + f + ' uploaded in bucket ' + sources_bucket)

    createBucket(s3,region, hostcerts_bucket)

# Provisions stack
def provision_stack(region, hostcerts_bucket, cacrypto_bucket, sources_bucket,vpcId):
    cf = boto3.client('cloudformation', region_name=region)
    cf.create_stack(StackName=stackname, TemplateURL='https://s3.amazonaws.com/' + sources_bucket + '/ipsec/templates/ipsec-setup.yaml',
                    Parameters=[
                        {'ParameterKey': 'QSS3BucketName', 'ParameterValue': sources_bucket},
                        {'ParameterKey': 'QSS3KeyPrefix', 'ParameterValue': 'ipsec/'},
                        {'ParameterKey': 'S3CaBucket', 'ParameterValue': cacrypto_bucket},
                        {'ParameterKey': 'S3ConfigsBucket', 'ParameterValue': sources_bucket},
                        {'ParameterKey': 'S3UserCertsBucket', 'ParameterValue': hostcerts_bucket},
                        {'ParameterKey': 'VpcId', 'ParameterValue': vpcId}],
                    Capabilities=['CAPABILITY_NAMED_IAM'])

    print('Stack ' + stackname + ' creation started. Waiting to finish (ca 3-5 min)')
    waiter = cf.get_waiter('stack_create_complete')
    try:
        waiter.wait(StackName=stackname)
    except Exception as err:
        raise Exception(
            'Error: Stack ' + stackname + ' in region ' + region + ' failed. Check AWS Console for more info')

    # Get the Output values
    outputs = cf.describe_stacks(StackName=stackname)['Stacks'][0]['Outputs']
    caCmkKey = outputs[1]['OutputValue']
    certEnrollLamnda = outputs[0]['OutputValue']

    print('Created CA CMK key ' + caCmkKey)
    print('Certificate generation lambda ' + certEnrollLamnda)

    return caCmkKey, certEnrollLamnda

# Generates a CA key and certificate
def generate_ca(region, hostcerts_bucket, cacrypto_bucket, leavecakey, caCmkKey, certEnrollLamnda):


    # Generate CA key pass with 128 Bytes
    rnd_bytes = os.urandom(128)
    rnd_token = base64.b64encode(rnd_bytes).decode('utf-8')

    # Generation the key and cert with openssl
    p = subprocess.Popen(
            # ECDSA for the future when libreswan supports it 
            # 'openssl ecparam -genkey -name secp384r1 | openssl ec -out ./ca.key.encrypted.pem  -passout pass:' + rnd_token + '  && openssl req -new -extensions v3_ca -sha256 -key ./ca.key.encrypted.pem -x509 -days 3650 -out ./cacert.pem -subj "/CN=ipsec.' + region + '" -passin pass:' + rnd_token,
            'openssl genrsa -aes256 -out ./ca.key.encrypted.pem  -passout pass:' + rnd_token + ' 4096 && openssl req -new -extensions v3_ca -sha256 -key ./ca.key.encrypted.pem -x509 -days 3650 -out ./cacert.pem -subj "/CN=ipsec.' + region + '" -passin pass:' + rnd_token,
        shell=True, stdout=subprocess.PIPE)
    p.wait()

    if p.returncode != 0:
        raise Exception('Error in execution of openssl script: ' + str(p.returncode))
    else:
        print('Certificate and key generated. Subject CN=ipsec.' + region + ' Valid 10 years')

    # Make cacrypto bucket
    s3 = boto3.client('s3', region_name=region)

    createBucket(s3, region, cacrypto_bucket)

    # Upload the encrypted key and CA cert
    f = open("ca.key.encrypted.pem",'rb')
    s3.put_object(Bucket=cacrypto_bucket, Key='ca.key.encrypted.pem', Body=f)
    print('Encrypted CA key uploaded in bucket ' + cacrypto_bucket)
    f = open("cacert.pem", 'rb')
    s3.put_object(Bucket=cacrypto_bucket, Key='ca.cert.pem', Body=f)
    print('CA cert uploaded in bucket ' + cacrypto_bucket)

    if leavecakey == 'yes':
        print('The CA certificate(cacert.pem) and key(cakey.pem) are in the local folder')
        print('Key encryption password follows on next line. Keep the password secret')
        print(rnd_token)
    else:
        os.remove('cacert.pem')
        os.remove('ca.key.encrypted.pem')
        print('CA cert and key remove from local folder')

    # Encrypt the key with CA CMK
    kms = boto3.client('kms', region_name=region)
    ency_token = base64.b64encode(kms.encrypt(KeyId=caCmkKey, Plaintext=rnd_token)['CiphertextBlob']).decode(
        encoding="utf-8")

    lmb = boto3.client('lambda', region_name=region)

    env = lmb.get_function_configuration(FunctionName=certEnrollLamnda)['Environment']
    env['Variables']['CA_PWD'] = ency_token
    boto3.client('lambda', region_name=region).update_function_configuration(FunctionName=certEnrollLamnda,
                                                                             Environment=env)
    print('Lambda function' + certEnrollLamnda + ' updated')
    
    # Restrict the CA key for encryption. Remove allow kms:encrypt action
    policy_response = kms.get_key_policy( KeyId=caCmkKey, PolicyName='default')
    kms.put_key_policy( KeyId=caCmkKey, PolicyName='default', Policy=policy_response['Policy'].replace('"kms:Encrypt",','') )
    print('Resource policy for CA CMK hardened - removed action kms:encrypt') 


#  Starts the main procedure
if __name__ == '__main__':
    import argparse, sys, time

    p = argparse.ArgumentParser(description="Enrolls IPSec encryption in AWS account")

    p.add_argument("--region", "-r", default="us-east-1",
                   metavar="<region>",
                   help="Region to provision (default:empty)")

    p.add_argument("--conf_sources_bucket", "-s", default="ipsec.configs.sources-[Random]",
                   metavar="<sources_bucket>",
                   help="Bucket to keep sources and Ipsec configs")

    p.add_argument("--hostcerts_bucket", "-p", default="ipsec.hostcerts-[Random]",
                   metavar="<hostcerts_bucket>",
                   help="Bucket to publish the hosts certs")

    p.add_argument("--cacrypto_bucket", "-c", default="ipsec.cacrypto.store-[Random]",
                   metavar="<cacrypto_bucher>",
                   help="Bucket with CA cert and encrypted key")

    p.add_argument("--ca_use_existing", "-e", default="no",
                   metavar="[yes|no]",
                   help="Reuse an existing CA cert and crypto key [no/yes]")

    p.add_argument("--stackname", "-n", default="ipsec-[Random]",
                   metavar="<stackname>",
                   help="Stackname")

    p.add_argument("--leave_cakey_in_folder", "-l", default="no",
                   metavar="[yes|no]",
                   help="Leaves a copy of CA key enincrypted in the current local folder. It can used for local backup.[no/yes]")

    p.add_argument("--vpc_id", "-v", default="any",
                   metavar="[vpc-id|any]",
                   help="Operate in provided vpc-id or in any vpc in the region (default)")
    
    print('Provisioning IPsec-Mesh version ' + code_version)
    print('\nUse --help for more options\n')

    args = p.parse_args()

    #   Make random chars to add to buckt name if needed
    chars = string.ascii_lowercase
    rnd = ''.join(random.sample(chars * 8, 8))

    #   Generate final bucket names if needed
    conf_sources_bucket = args.conf_sources_bucket.replace('[Random]', rnd)
    hostcerts_bucket = args.hostcerts_bucket.replace('[Random]', rnd)
    cacrypto_bucket = args.cacrypto_bucket.replace('[Random]', rnd)
    stackname = args.stackname.replace('[Random]', rnd)

    print('Arguments:')
    print('----------------------------')
    print('Region:                       ' + args.region)
    print('Vpc ID:                       ' + args.vpc_id)
    print('Hostcerts bucket:             ' + hostcerts_bucket)
    print('CA crypto bucket:             ' + cacrypto_bucket)
    print('Conf and sources bucket:      ' + conf_sources_bucket)
    print('CA use existing:              ' + args.ca_use_existing)
    print('Leave CA key in local folder: ' + args.leave_cakey_in_folder)
    print('AWS stackname:                ' + stackname)
    print('---------------------------- ')

    answer = raw_input('Do you want to proceed ? [yes|no]: ')
    if answer != 'yes':
        print('Did not provide "yes" answer,exiting...')
        quit()
    
    upload_files(args.region, hostcerts_bucket, conf_sources_bucket)
    
    caCmkKey, certEnrollLamnda = provision_stack(args.region, hostcerts_bucket, cacrypto_bucket, conf_sources_bucket, args.vpc_id)

    if args.ca_use_existing == 'no':
        generate_ca(args.region, hostcerts_bucket, cacrypto_bucket, args.leave_cakey_in_folder, caCmkKey,
                    certEnrollLamnda)

    print('done :-)')
