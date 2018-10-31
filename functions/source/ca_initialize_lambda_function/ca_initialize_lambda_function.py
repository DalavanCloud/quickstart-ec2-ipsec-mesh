#
# Initialization of CA with certificate and key. Updatesthe ca cert issue lamnbda function with ca password 
#
# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this
# software and associated documentation files (the "Software"), to deal in the Software
# without restriction, including without limitation the rights to use, copy, modify,
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
# 
import json, os, subprocess, base64, boto3, threading, logging
import cfnresponse 

def timeout(event, context):
    logging.error('Execution is about to time out, sending failure response to CloudFormation')
    cfnresponse.send(event, context, cfnresponse.FAILED, {}, None)

def lambda_handler(event, context):

    if event['RequestType'] == 'Delete':
        cfnresponse.send(event, context, cfnresponse.SUCCESS, {}, None)
        return
    # make sure we send a failure to CloudFormation if the function is going to timeout
    timer =  threading.Timer((context.get_remaining_time_in_millis() / 1000.00) - 0.5, timeout, args=[event, context])
    timer.start()
    status = cfnresponse.SUCCESS    
 
    try:
        region = event['ResourceProperties']['region']
        cacrypto_bucket = event['ResourceProperties']['cacrypto_bucket']    
        caCmkKey = event['ResourceProperties']['caCmkKey']    
        certEnrollLamnda = event['ResourceProperties']['certEnrollLamnda'] 
        print(event)
        print(cacrypto_bucket)
  
        # Generate CA key pass with 128 Bytes
        kmsclient = boto3.client('kms')
        print("Generating key password with KMS (128 Bytes)"); 
        random=kmsclient.generate_random(NumberOfBytes=128)
        rnd_token=base64.b64encode(random[u'Plaintext']).decode(encoding="utf-8")
        print("Generated ca password"); 
  
        # Generation the key and cert with openssl
        p = subprocess.Popen(
                'openssl genrsa -aes256 -out /tmp/ca.key.encrypted.pem  -passout pass:' + rnd_token + ' 4096 && openssl req -new -extensions v3_ca -sha256 -key /tmp/ca.key.encrypted.pem -x509 -days 3650 -out /tmp/cacert.pem -subj "/CN=ipsec.' + region + '" -passin pass:' + rnd_token,
            shell=True, stdout=subprocess.PIPE)
        p.wait()
        if p.returncode != 0:
            raise Exception('Error in execution of openssl script: ' + str(p.returncode))
        else:
            print('Certificate and key generated. Subject CN=ipsec.' + region + ' Valid 10 years')
      
        # Upload the encrypted key and CA cert
        f = open("/tmp/ca.key.encrypted.pem",'rb')
        s3 = boto3.client('s3', region_name=region)
        s3.put_object(Bucket=cacrypto_bucket, Key='ca.key.encrypted.pem', Body=f)
        print('Encrypted CA key uploaded in bucket ' + cacrypto_bucket)
        f = open("/tmp/cacert.pem", 'rb')
        s3.put_object(Bucket=cacrypto_bucket, Key='ca.cert.pem', Body=f)
        print('CA cert uploaded in bucket ' + cacrypto_bucket)
    
        os.remove('/tmp/cacert.pem')
        os.remove('/tmp/ca.key.encrypted.pem')
    
        # Encrypt the key with CA CMK
        kms = boto3.client('kms', region_name=region)
        ency_token = base64.b64encode(kms.encrypt(KeyId=caCmkKey, Plaintext=rnd_token)['CiphertextBlob']).decode(
            encoding="utf-8")
    
        lmb = boto3.client('lambda', region_name=region)
        env = lmb.get_function_configuration(FunctionName=certEnrollLamnda)['Environment']
        env['Variables']['CA_PWD'] = ency_token
        boto3.client('lambda', region_name=region).update_function_configuration(FunctionName=certEnrollLamnda, Environment=env)
        print('Lambda function' + certEnrollLamnda + ' updated')
        
        # Restrict the CA key for encryption. Remove allow kms:encrypt action
        policy_response = kms.get_key_policy( KeyId=caCmkKey, PolicyName='default')
        kms.put_key_policy( KeyId=caCmkKey, PolicyName='default', Policy=policy_response['Policy'].replace('"kms:Encrypt",','') )
        print('Resource policy for CA CMK hardened - removed action kms:encrypt') 
        
    except Exception as e:
        logging.error('Exception: %s' % e, exc_info=True)
        status = cfnresponse.FAILED
        
    finally:
        timer.cancel()
        cfnresponse.send(event, context, status, {}, None)

