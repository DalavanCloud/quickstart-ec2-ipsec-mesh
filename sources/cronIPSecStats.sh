#!/bin/bash
#
# Copyright 2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0#
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
