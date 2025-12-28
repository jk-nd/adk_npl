#!/bin/bash
# Add keycloak hostname to /etc/hosts for browser access

echo "Adding 'keycloak' hostname to /etc/hosts..."
echo "127.0.0.1 keycloak" | sudo tee -a /etc/hosts
echo "Done! You can now access Keycloak at http://keycloak:11000"

