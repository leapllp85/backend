#!/bin/bash

# SSL Certificate Generation Script for nginx
# This script generates self-signed certificates for development
# For production, replace with proper SSL certificates from a CA

set -e

CERT_DIR="/etc/nginx/ssl"
KEY_DIR="/etc/nginx/ssl"
DOMAIN=${SSL_DOMAIN:-localhost}
EXTERNAL_IP=${EXTERNAL_IP:-}

if [ -n "$EXTERNAL_IP" ]; then
    echo "Generating SSL certificates for IP address: $EXTERNAL_IP"
    CERT_SUBJECT="/C=US/ST=CA/L=San Francisco/O=Corporate MVP/OU=IT Department/CN=$EXTERNAL_IP"
else
    echo "Generating SSL certificates for domain: $DOMAIN"
    CERT_SUBJECT="/C=US/ST=CA/L=San Francisco/O=Corporate MVP/OU=IT Department/CN=$DOMAIN"
fi

# Create directories if they don't exist
mkdir -p "$CERT_DIR" "$KEY_DIR"

# Generate private key
if [ ! -f "$KEY_DIR/key.pem" ]; then
    echo "Generating private key..."
    openssl genrsa -out "$KEY_DIR/key.pem" 2048
    chmod 600 "$KEY_DIR/key.pem"
fi

# Generate certificate signing request
if [ ! -f "$CERT_DIR/cert.csr" ]; then
    echo "Generating certificate signing request..."
    openssl req -new -key "$KEY_DIR/key.pem" -out "$CERT_DIR/cert.csr" -subj "$CERT_SUBJECT"
fi

# Generate self-signed certificate with IP SAN support
if [ ! -f "$CERT_DIR/cert.pem" ]; then
    echo "Generating self-signed certificate..."
    
    # Create certificate extensions for IP addresses
    if [ -n "$EXTERNAL_IP" ]; then
        echo "Creating certificate with IP SAN extension..."
        cat > "$CERT_DIR/cert_extensions.conf" << EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req

[req_distinguished_name]

[v3_req]
subjectAltName = @alt_names

[alt_names]
IP.1 = $EXTERNAL_IP
IP.2 = 127.0.0.1
DNS.1 = localhost
EOF
        openssl x509 -req -days 365 -in "$CERT_DIR/cert.csr" -signkey "$KEY_DIR/key.pem" \
            -out "$CERT_DIR/cert.pem" -extensions v3_req -extfile "$CERT_DIR/cert_extensions.conf"
        rm "$CERT_DIR/cert_extensions.conf"
    else
        openssl x509 -req -days 365 -in "$CERT_DIR/cert.csr" -signkey "$KEY_DIR/key.pem" -out "$CERT_DIR/cert.pem"
    fi
    
    chmod 644 "$CERT_DIR/cert.pem"
fi

# Generate Diffie-Hellman parameters for enhanced security
if [ ! -f "$CERT_DIR/dhparam.pem" ]; then
    echo "Generating Diffie-Hellman parameters (this may take a while)..."
    openssl dhparam -out "$CERT_DIR/dhparam.pem" 2048
    chmod 644 "$CERT_DIR/dhparam.pem"
fi

echo "SSL certificates generated successfully!"
echo "Certificate: $CERT_DIR/cert.pem"
echo "Private Key: $KEY_DIR/key.pem"
echo "DH Parameters: $CERT_DIR/dhparam.pem"

# Verify certificate
echo "Certificate details:"
openssl x509 -in "$CERT_DIR/cert.pem" -text -noout | grep -E "(Subject:|Issuer:|Not Before:|Not After:|IP Address:|DNS:)"
