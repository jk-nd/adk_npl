#!/bin/bash
set -e

echo "🚀 Starting ADK-NPL Demo Stack"
echo "================================"

# Function to wait for a service to be healthy
wait_for_healthy() {
    local service=$1
    local max_attempts=60
    local attempt=0
    
    echo -n "Waiting for $service to be healthy..."
    while [ $attempt -lt $max_attempts ]; do
        if docker-compose ps $service | grep -q "healthy"; then
            echo " ✅"
            return 0
        fi
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo " ❌ Timeout!"
    docker-compose logs $service | tail -20
    return 1
}

# Function to wait for a service to complete (one-time jobs)
wait_for_complete() {
    local service=$1
    local max_attempts=120
    local attempt=0
    
    echo -n "Waiting for $service to complete..."
    while [ $attempt -lt $max_attempts ]; do
        local status=$(docker-compose ps $service --format json 2>/dev/null | jq -r '.[0].State' 2>/dev/null || echo "unknown")
        
        if [ "$status" = "exited" ]; then
            local exit_code=$(docker-compose ps $service --format json 2>/dev/null | jq -r '.[0].ExitCode' 2>/dev/null || echo "1")
            if [ "$exit_code" = "0" ]; then
                echo " ✅"
                return 0
            else
                echo " ❌ Failed with exit code $exit_code"
                docker-compose logs $service | tail -30
                return 1
            fi
        fi
        
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo " ❌ Timeout!"
    return 1
}

# Start databases first
echo ""
echo "Step 1: Starting databases..."
docker-compose up -d engine-db keycloak-db

wait_for_healthy engine-db
wait_for_healthy keycloak-db

# Start Keycloak
echo ""
echo "Step 2: Starting Keycloak..."
docker-compose up -d keycloak

wait_for_healthy keycloak

# Run Keycloak provisioning
echo ""
echo "Step 3: Provisioning Keycloak (realms, users)..."
docker-compose up -d keycloak-provisioning

wait_for_complete keycloak-provisioning

# Check if provisioning succeeded
if docker-compose logs keycloak-provisioning | grep -q "Apply complete"; then
    echo "   ✅ Keycloak provisioning completed successfully"
else
    echo "   ⚠️  Provisioning may have issues. Check logs:"
    docker-compose logs keycloak-provisioning | grep -E "(Error|Apply)" | tail -5
fi

# Start NPL Engine
echo ""
echo "Step 4: Starting NPL Engine..."
docker-compose up -d engine

wait_for_healthy engine

# Verify realms
echo ""
echo "Step 5: Verifying setup..."
echo -n "   Checking purchasing realm..."
if curl -s http://localhost:11000/realms/purchasing | grep -q '"realm":"purchasing"'; then
    echo " ✅"
else
    echo " ❌"
fi

echo -n "   Checking supplier realm..."
if curl -s http://localhost:11000/realms/supplier | grep -q '"realm":"supplier"'; then
    echo " ✅"
else
    echo " ❌"
fi

echo -n "   Checking NPL Engine..."
if curl -s http://localhost:12000/actuator/health | grep -q '"status":"UP"'; then
    echo " ✅"
else
    echo " ❌"
fi

echo ""
echo "================================"
echo "✅ Stack is ready!"
echo ""
echo "Next steps:"
echo "  • Start the demo: ./start_demo.sh"
echo "  • Run tests: ./run_tests.sh"
echo "  • Open UI: http://localhost:5173"
echo ""

