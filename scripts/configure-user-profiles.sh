#!/bin/bash
# Configure Keycloak User Profiles for custom attributes (organization, department)
# Required for Keycloak 26+ where User Profile controls allowed attributes

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:11000}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-welcome}"

echo "🔐 Getting admin token..."
ADMIN_TOKEN=$(curl -s -X POST "${KEYCLOAK_URL}/realms/master/protocol/openid-connect/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=${ADMIN_USER}&password=${ADMIN_PASSWORD}&grant_type=password&client_id=admin-cli" \
  | jq -r '.access_token')

if [ "$ADMIN_TOKEN" == "null" ] || [ -z "$ADMIN_TOKEN" ]; then
  echo "❌ Failed to get admin token"
  exit 1
fi

# User Profile JSON template with custom attributes
USER_PROFILE_JSON='{
  "attributes": [
    {
      "name": "username",
      "displayName": "${username}",
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": {
        "length": { "min": 3, "max": 255 },
        "username-prohibited-characters": {},
        "up-username-not-idn-homograph": {}
      }
    },
    {
      "name": "email",
      "displayName": "${email}",
      "required": { "roles": ["user"] },
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": { "email": {}, "length": { "max": 255 } }
    },
    {
      "name": "firstName",
      "displayName": "${firstName}",
      "required": { "roles": ["user"] },
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": { "length": { "max": 255 }, "person-name-prohibited-characters": {} }
    },
    {
      "name": "lastName",
      "displayName": "${lastName}",
      "required": { "roles": ["user"] },
      "permissions": { "view": ["admin", "user"], "edit": ["admin", "user"] },
      "validations": { "length": { "max": 255 }, "person-name-prohibited-characters": {} }
    },
    {
      "name": "organization",
      "displayName": "Organization",
      "multivalued": true,
      "permissions": { "view": ["admin", "user"], "edit": ["admin"] }
    },
    {
      "name": "department",
      "displayName": "Department",
      "multivalued": true,
      "permissions": { "view": ["admin", "user"], "edit": ["admin"] }
    }
  ],
  "groups": [
    {
      "name": "user-metadata",
      "displayHeader": "User metadata",
      "displayDescription": "Attributes, which refer to user metadata"
    }
  ]
}'

configure_realm() {
  local REALM=$1
  echo "📋 Configuring User Profile for realm: $REALM"
  
  RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/users/profile" \
    -d "$USER_PROFILE_JSON")
  
  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  
  if [ "$HTTP_CODE" == "200" ]; then
    echo "✅ User Profile configured for $REALM"
  else
    echo "⚠️ Response code: $HTTP_CODE for $REALM"
  fi
}

configure_user_attributes() {
  local REALM=$1
  local USERNAME=$2
  local ORG=$3
  local DEPT=$4
  
  echo "👤 Setting attributes for $USERNAME in $REALM..."
  
  # Get user ID
  USER_DATA=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/users?username=${USERNAME}")
  USER_ID=$(echo "$USER_DATA" | jq -r '.[0].id')
  
  if [ "$USER_ID" == "null" ] || [ -z "$USER_ID" ]; then
    echo "⚠️ User $USERNAME not found in $REALM"
    return
  fi
  
  # Get current user and add attributes
  CURRENT_USER=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${USER_ID}")
  
  UPDATED_USER=$(echo "$CURRENT_USER" | jq --arg org "$ORG" --arg dept "$DEPT" \
    '. + {"attributes":{"organization":[$org],"department":[$dept]}}')
  
  curl -s -X PUT \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/users/${USER_ID}" \
    -d "$UPDATED_USER"
  
  echo "✅ Attributes set for $USERNAME"
}

fix_protocol_mapper() {
  local REALM=$1
  local CLIENT_ID_NAME=$2
  local MAPPER_NAME=$3
  
  echo "🔧 Fixing protocol mapper: $MAPPER_NAME in $REALM/$CLIENT_ID_NAME..."
  
  # Get client ID
  CLIENT_UUID=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/clients?clientId=${CLIENT_ID_NAME}" | jq -r '.[0].id')
  
  if [ "$CLIENT_UUID" == "null" ]; then
    echo "⚠️ Client $CLIENT_ID_NAME not found"
    return
  fi
  
  # Get mapper
  MAPPERS=$(curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/protocol-mappers/models")
  
  MAPPER=$(echo "$MAPPERS" | jq -r --arg name "$MAPPER_NAME" '.[] | select(.name == $name)')
  MAPPER_ID=$(echo "$MAPPER" | jq -r '.id')
  
  if [ "$MAPPER_ID" == "null" ] || [ -z "$MAPPER_ID" ]; then
    echo "⚠️ Mapper $MAPPER_NAME not found"
    return
  fi
  
  # Update mapper config
  UPDATED_MAPPER=$(echo "$MAPPER" | jq '.config["multivalued"] = "true" | .config["aggregate.attrs"] = "true" | .config["jsonType.label"] = "String"')
  
  curl -s -X PUT \
    -H "Authorization: Bearer $ADMIN_TOKEN" \
    -H "Content-Type: application/json" \
    "${KEYCLOAK_URL}/admin/realms/${REALM}/clients/${CLIENT_UUID}/protocol-mappers/models/${MAPPER_ID}" \
    -d "$UPDATED_MAPPER"
  
  echo "✅ Mapper $MAPPER_NAME fixed"
}

echo "=================================="
echo "Configuring Keycloak User Profiles"
echo "=================================="

# Configure user profiles for both realms
configure_realm "purchasing"
configure_realm "supplier"

# Fix protocol mappers
echo ""
echo "🔧 Fixing protocol mappers..."
fix_protocol_mapper "purchasing" "purchasing" "organization-mapper"
fix_protocol_mapper "purchasing" "purchasing" "department-mapper"
fix_protocol_mapper "supplier" "supplier" "organization-mapper"
fix_protocol_mapper "supplier" "supplier" "department-mapper"

# Set user attributes
echo ""
echo "👤 Setting user attributes..."
configure_user_attributes "purchasing" "purchasing_agent" "Acme Corp" "Procurement"
configure_user_attributes "supplier" "supplier_agent" "Supplier Inc" "Sales"

echo ""
echo "✅ Configuration complete!"

