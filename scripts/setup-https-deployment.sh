#!/bin/bash

# HTTPS Deployment Setup Script
# Sets up Supervisor with Nginx HTTPS on port 8000

set -e

echo "=================================="
echo "HTTPS Deployment Setup"
echo "=================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Install required packages
echo "Installing required packages..."
apt-get update
apt-get install -y nginx supervisor openssl

# Create necessary directories
echo "Creating directories..."
mkdir -p /etc/nginx/ssl
mkdir -p /var/log/supervisor
mkdir -p /var/log/nginx
mkdir -p /var/www/certbot
mkdir -p staticfiles
mkdir -p media

# Set permissions
chmod 755 /etc/nginx/ssl
chmod 755 /var/log/supervisor
chmod 755 /var/log/nginx

# Copy nginx HTTPS configuration
echo "Configuring Nginx for HTTPS..."
if [ -f "nginx-https.conf" ]; then
    cp nginx-https.conf /etc/nginx/nginx.conf
    echo "✓ Nginx HTTPS configuration installed"
else
    echo "✗ nginx-https.conf not found in /app"
    exit 1
fi

# Make SSL certificate generation script executable
echo "Setting up SSL certificate generation..."
if [ -f "scripts/generate-ssl-certs.sh" ]; then
    chmod +x scripts/generate-ssl-certs.sh
    echo "✓ SSL certificate script is executable"
else
    echo "✗ generate-ssl-certs.sh not found"
    exit 1
fi

# Generate SSL certificates
echo "Generating SSL certificates..."
scripts/generate-ssl-certs.sh

# Test Nginx configuration
echo "Testing Nginx configuration..."
nginx -t
if [ $? -eq 0 ]; then
    echo "✓ Nginx configuration is valid"
else
    echo "✗ Nginx configuration test failed"
    exit 1
fi

# Copy Supervisor configuration
echo "Configuring Supervisor..."
if [ -f "supervisord.conf" ]; then
    cp supervisord.conf /etc/supervisor/conf.d/app.conf
    echo "✓ Supervisor configuration installed"
else
    echo "✗ supervisord.conf not found in /app"
    exit 1
fi

# # Create django user if doesn't exist
# if ! id "django" &>/dev/null; then
#     echo "Creating django user..."
#     useradd -r -s /bin/bash django
#     echo "✓ Django user created"
# fi

# # Set ownership
# echo "Setting file ownership..."
# chown -R django:django staticfiles
# chown -R django:django media
# chown -R django:django /var/log/supervisor

# Reload Supervisor
echo "Reloading Supervisor..."
supervisorctl reread
supervisorctl update

# Start services
echo "Starting services..."
supervisorctl start ssl-cert-generator
# supervisorctl start django
supervisorctl start nginx
