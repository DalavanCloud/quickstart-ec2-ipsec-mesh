#
#   Triggers SSM start commant to enroll certicates on selected instances 
#   
#   Configuration in enviroment variables
#       - Selector is Tag and Value from the enviroment variable.
#       - Certificate issuing lambda 
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
import os, time, json

def lambda_handler(event, context):

    IPSecSetupLambda=os.environ['IPSecSetupLambda']
    SelectorTagName=os.environ['SelectorTagName']
    SelectorTagValue=os.environ['SelectorTagValue']
    region=os.environ['AWS_REGION']
    
    print('enrolling new certificates on instances with Tag '+SelectorTagName+':'+SelectorTagValue)
    
    ec2 = boto3.client('ec2')
    response = ec2.describe_instances(
         Filters=[{"Name":"tag:"+SelectorTagName,"Values":[SelectorTagValue]} ])
    
    for res in response['Reservations']:
        for i in res['Instances']:
            print("enrolling new certificate on instance "+ i['InstanceId'])
                                                         
            client = boto3.client('lambda')
            r = client.invoke(
                 FunctionName=IPSecSetupLambda,    
                 InvocationType='Event',
                 LogType='Tail',                 
                 Payload=json.dumps({ "detail" :  { "instance-id": i['InstanceId']}, "certificate_only":"true"}))
