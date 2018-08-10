#!/bin/bash
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
##

region=`curl --silent http://169.254.169.254/latest/dynamic/instance-identity/document | grep region | cut -f 4 -d '"'`

# Count of active IPSec SA bidirectional
t=`sudo ipsec whack --globalstatus | grep "current.states.ipsec"  | sed "s/^.*=//"`
aws cloudwatch put-metric-data --metric-name IPSec-Connections --namespace IPSec --dimensions InstanceID="INSTANCE" --value "$t"  --region $region

# Total count of Errors
t=`sudo ipsec whack --globalstatus | grep -i error | sed "s/^.*=//" | awk '{n += $1}; END{print n}'`
aws cloudwatch put-metric-data --metric-name IPSec-IKE-Errors --namespace IPSec --dimensions InstanceID="INSTANCE" --value "$t"  --region $region

# Count of active IKE Shunts bidirectional
t=`sudo ipsec whack --globalstatus | grep "current.states.shunts"  | sed "s/^.*=//"`
aws cloudwatch put-metric-data --metric-name IPSec-Connection-Shunts --namespace IPSec --dimensions InstanceID="INSTANCE" --value "$t"  --region $region

sudo ipsec whack --clearstats
