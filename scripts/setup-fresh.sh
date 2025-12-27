#!/bin/bash
set -e

echo "🧹 Clean Restart of ADK-NPL Demo"
echo "================================"
echo ""

# Step 1: Stop everything
echo "1️⃣  Stopping all services..."
docker-compose down
echo "   ✅ Stopped"

# Step 2: Wipe volumes
echo ""
echo "2️⃣  Removing old data..."
docker volume rm -f adk-demo_keycloak-db adk-demo_keycloak-provisioning 2>/dev/null || true
echo "   ✅ Volumes removed"

# Step 3: Verify password in .env
echo ""
echo "3️⃣  Checking .env configuration..."
if grep -q "SEED_TEST_USERS_PASSWORD=Welcome123" .env 2>/dev/null; then
    echo "   ✅ Password is correct (Welcome123)"
elif grep -q "SEED_TEST_USERS_PASSWORD=welcome" .env 2>/dev/null; then
    echo "   ⚠️  Password needs updating..."
    sed -i '' 's/SEED_TEST_USERS_PASSWORD=welcome/SEED_TEST_USERS_PASSWORD=Welcome123/' .env
    echo "   ✅ Updated to Welcome123"
else
    echo "   ⚠️  Cannot read .env (checking .env.example)..."
fi

# Step 4: Start databases
echo ""
echo "4️⃣  Starting databases..."
docker-compose up -d engine-db keycloak-db
echo -n "   Waiting for databases"
for i in {1..30}; do
    if docker-compose ps engine-db keycloak-db 2>&1 | grep -q "healthy.*healthy"; then
        echo " ✅"
        break
    fi
    echo -n "."
    sleep 1
done

# Step 5: Start Keycloak
echo ""
echo "5️⃣  Starting Keycloak..."
docker-compose up -d keycloak
echo -n "   Waiting for Keycloak"
for i in {1..60}; do
    if docker-compose ps keycloak 2>&1 | grep -q "healthy"; then
        echo " ✅"
        break
    fi
    echo -n "."
    sleep 1
done

# Step 6: Run provisioning
echo ""
echo "6️⃣  Provisioning Keycloak (creating realms and users)..."
docker-compose up -d keycloak-provisioning
echo -n "   Waiting for provisioning"
for i in {1..120}; do
    if docker-compose logs keycloak-provisioning 2>&1 | grep -q "Apply complete"; then
        echo " ✅"
        PROV_SUCCESS=1
        break
    fi
    if docker-compose ps keycloak-provisioning --format json 2>/dev/null | grep -q '"State":"exited"'; then
        # Check if it failed
        if docker-compose logs keycloak-provisioning 2>&1 | grep -q "Error:"; then
            echo " ❌"
            echo ""
            echo "   Provisioning errors:"
            docker-compose logs keycloak-provisioning 2>&1 | grep -A 2 "Error:" | head -10
            exit 1
        fi
    fi
    echo -n "."
    sleep 1
done

if [ -z "$PROV_SUCCESS" ]; then
    echo " ⚠️  Timeout - checking logs..."
    docker-compose logs keycloak-provisioning | tail -20
fi

# Step 6.5: Configure User Profiles (required for Keycloak 26+)
echo ""
echo "   Configuring User Profiles for custom attributes..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/configure-user-profiles.sh" ]; then
    "$SCRIPT_DIR/configure-user-profiles.sh"
else
    echo "   ⚠️  configure-user-profiles.sh not found, skipping"
fi

# Step 7: Start Engine
echo ""
echo "7️⃣  Starting NPL Engine..."
docker-compose up -d engine
echo -n "   Waiting for Engine"
for i in {1..60}; do
    if docker-compose ps engine 2>&1 | grep -q "healthy"; then
        echo " ✅"
        break
    fi
    echo -n "."
    sleep 1
done

# Step 8: Verify
echo ""
echo "8️⃣  Verifying setup..."
sleep 2

echo -n "   Purchasing realm: "
if curl -s http://localhost:11000/realms/purchasing 2>/dev/null | grep -q '"realm":"purchasing"'; then
    echo "✅"
else
    echo "❌"
fi

echo -n "   Supplier realm: "
if curl -s http://localhost:11000/realms/supplier 2>/dev/null | grep -q '"realm":"supplier"'; then
    echo "✅"
else
    echo "❌"
fi

echo -n "   NPL Engine: "
if curl -s http://localhost:12000/actuator/health 2>/dev/null | grep -q '"status":"UP"'; then
    echo "✅"
else
    echo "❌"
fi

echo ""
echo "================================"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  • For frontend UI: Run ./setup_hosts.sh (adds keycloak hostname)"
echo "  • Test agents:"
echo "    python test_purchasing_agent.py"
echo "    python test_supplier_agent.py"
echo ""

