#
# Triggers SSM start commant to enroll certicates on selected instances 
#   
# Selector is Tag and Value from the enciroment variable 
#
# Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.
#
import boto3
import os, time,json

def lambda_handler(event, context):

    SelectorTagName=os.environ['SelectorTagName']
    SelectorTagValue=os.environ['SelectorTagValue']
    ResultTagValue=os.environ['ResultTagValue']
    SourceBucket=os.environ['SourceBucket']
    CertificateEnrollLambda=os.environ['CertificateEnrollLambda']
    IPSecSetUpScript=os.environ['IPSecSetUpScript']
    VpcId=os.environ['VpcId']
    
    ec2 = boto3.resource('ec2')
    s3 =  boto3.client('s3')
    
    obj = s3.get_object(Bucket=SourceBucket, Key=IPSecSetUpScript)
    template=obj['Body'].read().decode('utf-8') 
    
    
    print('checking instance '+event["detail"]["instance-id"])
    ec2 = boto3.resource('ec2')
    r = ec2.Instance(id=event["detail"]["instance-id"])

    if r.state["Code"] !=16 :
         raise Exception('Failed. Instance '+ r.instance-id + ' is not running ( state:' + str(r.state["Name"]) + ')')

    # check if the right vpc-id           
    if  VpcId != "any":
        if r.vpc_id != VpcId:
            print("Instance is in VPC " + r.vpc_id + " but operation restricted via params to VPC " + VpcId +  " Exit")
            return 
         
    for tag in r.tags:
        if tag['Key'] == SelectorTagName and ( tag['Value'] == SelectorTagValue or ( tag['Value'] == ResultTagValue and "certificate_only" in event)):    
            # We need to  setup IPSec 
            print('starting the IPSec configration and/or certificate enrollment on instances ' + r.id )
            
            ssm = boto3.client('ssm')
            
            # wait 120 sec max for the SSM agent on instance to become online 
            repeat=10
            while len(ssm.describe_instance_information(InstanceInformationFilterList= [{'key': 'InstanceIds', 'valueSet': [r.id]}, 
                                                                                        {'key': 'PingStatus',  'valueSet': ['Online']}] )['InstanceInformationList']) < 1 and repeat > 0:
                time.sleep(12)
                repeat=repeat-1
            
            if repeat==0:
                raise Exception('Instance not reachable in SSM. Check Instanc e Roles, SSM Agent or SecGroups')
            
            try:
                
                # Issue a certificate for the host
                client = boto3.client('lambda')

                cert_r = client.invoke(
                    FunctionName=CertificateEnrollLambda,
                    InvocationType='RequestResponse',
                    LogType='Tail',
                    Payload=json.dumps({"instance-id": r.id})
                )

                t = cert_r['Payload']
                j = json.load(t)
                
                print('certificate genenerated')
                
                #  templates. change placeholder with values
                if "certificate_only" in event:
                    certonly="true"
                    print('doing certificate reenrollment only')
                else:
                    certonly="false"
                    print('doing ipsec setup and cert enrollment')

                script=template.replace("{{configBucket}}",SourceBucket).replace("{{certificate}}",json.dumps(j)).replace("{{certificate_only}}",certonly)
                print('script template run')
                response=ssm.send_command(
                    InstanceIds = [r.id],
                    #Targets= [{"Key":"tag:"+SelectorTagName,"Values":[SelectorTagValue]} ],
                    DocumentName='AWS-RunShellScript',
                    TimeoutSeconds=3600,
                    Comment='Initial IPSec setup with cert enrollment',
                    Parameters={"commands":[script],"executionTimeout":["600"],"workingDirectory":["/tmp/"]},
                    MaxConcurrency='5',
                    MaxErrors='5',
                )
    
                cmdId = response['Command']['CommandId']
                print('Started IPSec config in CommandId: ' + cmdId)
                
            except Exception as err:
	            raise err
            
            response = ssm.list_commands(CommandId=cmdId)
            
            while response['Commands'][0]['CompletedCount'] != response['Commands'][0]['TargetCount']:
                time.sleep(10)
                
                response = ssm.list_commands(CommandId=cmdId)
    
            if response['Commands'][0]['ErrorCount'] != 0:
                  raise Exception('Failed. Confguring IPSec on the instance failed. Check Output Log of E2 SSM Command Id '+ cmdId + '')
            
            ec2 = boto3.client('ec2')
            r = ec2.delete_tags(Resources=[event["detail"]["instance-id"]],Tags=[{"Key": SelectorTagName,"Value":SelectorTagValue}])
            r = ec2.create_tags(Resources=[event["detail"]["instance-id"]],Tags=[{"Key": SelectorTagName,"Value":ResultTagValue}])
            
    print('IPsec configuration exit')
    
