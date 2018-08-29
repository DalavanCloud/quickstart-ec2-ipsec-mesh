#!/bin/bash
# 
#	
#   Enrolls certificate,installs and setups ipsec
#
#  Variable needed	
#		configBucket		- Config Bucket name. The keys (files names) are predefines: 
#		oe-conf.conf   		- configration of the oppurtonistic ipsec
#	       	private 		- list of networks with mandaqtory protection
#		clear			- list of netowrks to communication without encryption	
#		installCert.py		- script to enroll certifcates
#		cronIPSecStats.sh	- srcript that collects statistics
#		cron.txt		- cron job definition
#		generateCertbundleLambda - Lambda name for the certifcate generation. 
#
#    Copyright 2017-2018 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
#   Licensed under the Apache License, Version 2.0 (the "License").
#   You may not use this file except in compliance with the License.
#   A copy of the License is located at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#   or in the "license" file accompanying this file. This file is distributed
#   on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
#   express or implied. See the License for the specific language governing
#   permissions and limitations under the License.
#
##

set -u

# put here the bucket and lambda name 
configBucket="{{configBucket}}"
certificate='{{certificate}}'
certificate_only='{{certificate_only}}'


install_certificate () {

	region=`curl --silent http://169.254.169.254/latest/dynamic/instance-identity/document | grep region | cut -f 4 -d '"'`

	echo $certificate | ./jq  .CERT_P12_B64 | base64 -i -d > ./cert.p12
	if [ $? -ne 0 ]; then
		echo "Error: Failed to extract certifcate from variable"
		exit 10 
	fi

	echo $certificate | ./jq  .CERT_P12_ENCRYPTED_PWD  |  base64 -i -d > ./tmp
	password=`aws kms decrypt --ciphertext-blob fileb://tmp --region "$region" | ./jq .Plaintext | base64 -d -i | tr -d '"'`
	if [ $? -ne 0 ]; then
		echo "Error: Failed to decrypt the password"
		exit 11 
	fi
	rm ./tmp
        rm /etc/ipsec.d/*db || echo ok

    	ipsec initnss

    	pk12util -i ./cert.p12 -d sql:/etc/ipsec.d -W "$password"
	if [ $? -ne 0 ]; then
		echo "Error: Failed to install certifcate"
		exit 5
	fi
	echo "certificate installed successful"
}


# config and files will be stored in folder /root/ipsec 
cd /root
mkdir ipsec || echo "ignorre"  
cd ipsec


if [ $certificate_only == "true" ]; then
	install_certificate
	#sudo ipsec restart
	exit 0
fi 

pip --version || curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && sudo python get-pip.py
curl https://stedolan.github.io/jq/download/linux64/jq > jq && chmod 755 jq 
aws --version || sudo pip install boto3 awscli 
if [ $? -ne 0 ]; then 
	echo "Error: (PIP, boto3 or awscli) can not be installed"
	exit 1
fi 

sudo yum -y install libreswan curl
if [ $? -ne 0 ]; then 
	echo "Error: (Libreswan or curl) can not be installed"
	exit 2
fi

# download ipsec policies
aws s3 cp "s3://$configBucket/config/private" . && \
aws s3 cp "s3://$configBucket/config/private-or-clear" . && \
aws s3 cp "s3://$configBucket/config/clear-or-private" . && \
aws s3 cp "s3://$configBucket/config/clear" . && \
aws s3 cp "s3://$configBucket/config/oe-cert.conf" . && \
if [ $? -ne 0 ]; then
	echo "Error: Failed to download configs from s3://$configBucket files: oe-cert.conf, private, clear "
	exit 4
fi

# download the ipsec statistics
aws s3 cp "s3://$configBucket/sources/cronIPSecStats.sh" . && \
aws s3 cp "s3://$configBucket/sources/cron.txt" .
if [ $? -ne 0 ]; then
	echo "Error: Failed to download IPSec stats scripts from s3://$configBucket files: cronIPSecStats.sh and cron.txt "
	exit 9
fi

# copy policy to ipsec folder
sudo cp private /etc/ipsec.d/policies/private && \
sudo cp private-or-clear /etc/ipsec.d/policies/private-or-clear && \
sudo cp clear-or-private /etc/ipsec.d/policies/clear-or-private && \
sudo cp clear /etc/ipsec.d/policies/clear && \
sudo cp oe-cert.conf /etc/ipsec.d/oe-cert.conf
if [ $? -ne 0 ]; then
	echo "Error: Failed to copy localy files: oe-cert.conf, private, clear "
	exit 6
fi

# enroll certificate 
install_certificate
sudo ipsec restart
if [ $? -ne 0 ]; then
	echo "Error: Failed to restart ipsec"
	exit 7 
fi

i=`curl http://169.254.169.254/latest/meta-data/instance-id`
sed -i.bak "s/INSTANCE/$i/" cronIPSecStats.sh 
chmod 755 cronIPSecStats.sh
# install statistics with cronjob
sudo crontab ./cron.txt
if [ $? -ne 0 ]; then
	echo "Error: Failed to install cron job"
	exit 8 
fi
