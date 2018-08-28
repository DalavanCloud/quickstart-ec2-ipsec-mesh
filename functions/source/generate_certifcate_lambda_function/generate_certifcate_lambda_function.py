"""
    Certificate encrolling function: generates key, certificate request and issues/signs with CA

   This is a wraper around bash function that issues certifcate 
   and uploads certificate to predefined bucket

   Input 
	  - instance-id   (instance_id)
	  - enviroment variable to set: 
	      CA_BUCKET     - the bucket of CA signing cert
	      CA_FILE       - the key (aka file) where the CA cert is
	      CA_KEY_FILE   - file with CA private key 
	      CA_PWD        - password for the CA private key KMS encrypted
	      CERTS_BUCKET  - bucket where the certs will be updaloed 
	      P12_CMS_KEYID - CMS KeyId to encrypt the P12 export password

   Output is JSON structure containing

    { 	ERR:  		               	error text if exit code not 0, 
	      CERT_PEM_B64:          	certifcate in pem format encoded base64,
	      CERT_P12_B64:	          certificate in p12 format encode64
	      CERT_P12_ENCRYPTED_PWD  // encrypted P12 password (CiphertextBlob) with P12_CMS_KEYID
	   
    }

    Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
   
    Licensed under the Apache License, Version 2.0 (the "License").
    You may not use this file except in compliance with the License.
    A copy of the License is located at
   
   http://www.apache.org/licenses/LICENSE-2.0
  
   or in the "license" file accompanying this file. This file is distributed
   on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
   express or implied. See the License for the specific language governing
   permissions and limitations under the License.
   
"""
import subprocess,os, base64,json, datetime
import boto3

def lambda_handler(event, context):

    print("Creating certificate for " + event['instance-id']);
    
    bucket = os.environ['CA_BUCKET'];
    cacertfile = os.environ['CA_FILE'];
    cakeyfile = os.environ['CA_KEY_FILE'];
    certsbucket = os.environ['CERTS_BUCKET'];
    p12_cms_keyid = os.environ['P12_CMS_KEYID'];
    capwd = os.environ['CA_PWD'];
    
    s3client =  boto3.client('s3')
    
    print("Downloading: CA certicate");
    obj = s3client.get_object(Bucket=bucket, Key=cacertfile)
    cacertificate=obj['Body'].read().decode('utf-8') 
    print("Downloaded: CA certicate");
    
    print("Downloading: CA encrypted key");
    obj = s3client.get_object(Bucket=bucket, Key=cakeyfile)
    cakey=obj['Body'].read().decode('utf-8') 
    print("Downloaded: CA encrypted key");
    
    os.environ['CA_CERT'] = cacertificate;
    os.environ['CA_KEY'] = cakey;
    
    kmsclient = boto3.client('kms')

    print("Generating: export password with KMS (128 Bytes)"); 
    random=kmsclient.generate_random(NumberOfBytes=128)
    exportpassword=base64.b64encode(random[u'Plaintext']).decode(encoding="utf-8")
    print("Generated: export password"); 


    print("Encrypting: password with KMS"); 
    p12_pwd=kmsclient.encrypt(KeyId=p12_cms_keyid, Plaintext=exportpassword)
    print("Encrypted: export password with KMS"); 
    
    print("Decrypting: CA key password");
    cakey_password = kmsclient.decrypt(CiphertextBlob=base64.b64decode(capwd))['Plaintext'].decode(encoding="utf-8")
    print("Decrypted: CA key password");
    
    # get the instance IPs and hostname 
    SAN=""
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(event['instance-id'])
    hostname=instance.private_dns_name
    for int in instance.network_interfaces_attribute:
        for net in int['PrivateIpAddresses']:
            if SAN != "": 
                SAN=SAN + ",IP:"+net['PrivateIpAddress']
            else:
                SAN="IP:" + net['PrivateIpAddress']
    print("adding follwing IP to certificate " + SAN)
    print("hostname " + hostname)
    os.environ['SAN'] = SAN
    
    os.environ['CA_PWD_DECRYPTED'] = cakey_password
    os.environ['CERT_EXPORT_PWD'] = exportpassword
    
    print("Issuing: certificate with openssl");
    p = subprocess.Popen('sh ./genCert.sh '+ hostname, shell=True, stdout=subprocess.PIPE)
    p.wait()
    os.environ['CA_PWD_DECRYPTED'] = "------------";
    
    if p.returncode != 0: 
        raise Exception('Error in execution of openssl script with exit code:' + str(p.returncode))
    
    print("Issued: Script finished");
    r=''    
    for line in p.stdout:
      r=r + line.decode(encoding="utf-8")
    
    print("Converting: script output to JSON");
    j=json.loads(r.replace(" ",""))
    print("Converted: output to JSON");

    d = str(datetime.datetime.now())
    
    print('Uploading: generated cert to bucket '+certsbucket)
    s3client.put_object(Bucket=certsbucket, Key=d+' - ' + hostname+ '.pem', ServerSideEncryption="AES256", Body=base64.b64decode(j['CERT_PEM_B64']))
    print("Uploaded: certificate to Bucket s3://" + certsbucket + ' Key:' + d + ' - ' + hostname + '.pem')
                                
    j['CERT_P12_ENCRYPTED_PWD'] = base64.b64encode(p12_pwd['CiphertextBlob']).decode(encoding="utf-8")
    print("SUCCESS: Certificate issued")

    return(j)
    
    
