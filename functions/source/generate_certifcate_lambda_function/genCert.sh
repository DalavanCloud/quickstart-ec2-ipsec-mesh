#! /bin/bash
#
#   Generate key, certificate request and issues/signs with CA
#   
#   The script provides all in one, you do not need openssl config, index etc
#
#   Input 
#	- command line hostname
#	- enviroment variable CA_CERT, CA_KEY, CA_PWD, EXPORT_PWD, SAN
#
#   Output is JSON structure containing
#
#    { 	ERR:  		        error text if exit code not 0, 
#	      CERT_PEM_B64:   certifcate in pem format encoded base64,
#	      CERT_P12_B64:	  certificate in p12 format encode64
#    }
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
##
hostname=$1

openssl='

[ req ]
default_bits        = 4096
default_keyfile     = ca-key.pem
distinguished_name  = subject
string_mask         = utf8only

[subject]

[ usr_cert ]

subjectKeyIdentifier    = hash
authorityKeyIdentifier  = keyid,issuer
basicConstraints        = CA:FALSE
keyUsage            	= digitalSignature, keyEncipherment
subjectAltName          = ${ENV::SAN}

[ ca ]
default_ca = CA_default

[ CA_default ]
# Directory and file locations.
dir               = .
certs             = $dir/
crl_dir           = $dir/crl
new_certs_dir     = $dir/
database          = $dir/index.txt
serial            = $dir/serial

# The root key and root certificate.
private_key       = $dir/ca.cert.key.pem
certificate       = $dir/ca.cert.pem

# SHA-1 is deprecated, so use SHA-2 instead.
default_md        = sha256

name_opt          = ca_default
cert_opt          = ca_default
default_days      = 30
preserve          = no
policy            = policy_strict
x509_extensions   = usr_cert

[ policy_strict ]
countryName             = optional
stateOrProvinceName     = optional
organizationName        = optional
organizationalUnitName  = optional
commonName              = supplied
emailAddress            = optional

'

if [[ -z "${CA_CERT}" ]] || [[ -z "${CA_KEY}" ]]  || [[ -z "${CERT_EXPORT_PWD}" ]] ; then
    print "{ \"ERR\":\"Some env variables not defined \", \"CERT_PEM_B64\":\"\",\"CERT_P12_B64\":\"\" }"
    exit 5
fi

# write on to temp (TO DO can wire write elsewhere)
cd /tmp
printf "%016x\n" $RANDOM$RANDOM$RANDOM > serial
rm index.txt
touch index.txt
echo "$openssl" > ./openssl.conf
echo "$CA_CERT" > ./ca.cert.pem
echo "$CA_KEY"  > ./ca.cert.key.pem

# Generating key and cert request
openssl req -new -newkey rsa:4096 -nodes -subj "/CN=$hostname" -out ./req.pem -keyout ./key.pem -config ./openssl.conf > /dev/null
# Using ECDSA when libreswan supports it 
# openssl ecparam -genkey -name secp384r1 -out ./key.pem > /dev/null && openssl req -new -subj "/CN=$hostname" -out ./req.pem -key ./key.pem -config ./openssl.conf > /dev/null

# Check if we have an error
if [ $? -ne 0 ]; then
    printf "{ \"ERR\":\"Can not generate certificate key and reques\", \"CERT_PEM_B64\":\"\",\"CERT_P12_B64\":\"\" }"
    exit 1
fi

# Signing
openssl ca -config ./openssl.conf -in ./req.pem -out ./cert.pem -batch  -passin pass:$CA_PWD_DECRYPTED > /dev/null
# Check if we have an error
if [ $? -ne 0 ]; then
    printf "{ \"ERR\":\"Can not sign the request\", \"CERT_PEM_B64\":\"\",\"CERT_P12_B64\":\"\" }"
    exit 2
fi

# Exporting to p12
openssl pkcs12 -export -name hostcert -certfile ./ca.cert.pem   -in ./cert.pem  -inkey ./key.pem -out ./cert.p12 -aes256 -passout pass:"$CERT_EXPORT_PWD" > /dev/null
# Check if we have an error
if [ $? -ne 0 ]; then
    printf "{ \"ERR\":\"Can not export the certificate to PKCS12\", \"CERT_PEM_B64\":\"\",\"CERT_P12_B64\":\"\" }"
    exit 3
fi

cert_p12_b64=`base64 ./cert.p12`
cert_pem_b64=`base64 ./cert.pem`
# Output JSON with Cert PEM and Cert PKCS12 both encoded with BASE64
echo '{ "ERR":"", "CERT_PEM_B64":"'$cert_pem_b64'","CERT_P12_B64":"'$cert_p12_b64'" }'

# Removng keys and certs
rm *
