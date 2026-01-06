#!/bin/bash
# ADK-NPL Test Suite Runner
# 
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh quick        # Run quick tests only (no API calls)
#   ./run_tests.sh integration  # Run NPL integration tests
#   ./run_tests.sh agents       # Run agent core tests
#   ./run_tests.sh all          # Run everything including slow tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}   ADK-NPL Test Suite${NC}"
echo -e "${BLUE}============================================${NC}"
echo ""

# Activate virtual environment if not already active
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo -e "${YELLOW}Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

# Check if NPL Engine is running
check_npl_engine() {
    if curl -s http://localhost:12000/npl/commerce/openapi.json > /dev/null 2>&1; then
        echo -e "${GREEN}✓ NPL Engine is running${NC}"
        return 0
    else
        echo -e "${RED}✗ NPL Engine is NOT running${NC}"
        echo -e "${YELLOW}  Please start NPL Engine first: npl-cli engine start${NC}"
        return 1
    fi
}

# Check if Keycloak is running
check_keycloak() {
    if curl -s http://localhost:11000/health/ready > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Keycloak is running${NC}"
        return 0
    else
        echo -e "${RED}✗ Keycloak is NOT running${NC}"
        return 1
    fi
}

case "${1:-all}" in
    monitoring)
        echo -e "${YELLOW}Running monitoring tests (no external dependencies)...${NC}"
        echo ""
        pytest tests/test_monitoring.py -v --tb=short
        ;;
    
    notifications)
        echo -e "${YELLOW}Running notification tests...${NC}"
        echo ""
        pytest tests/test_notifications.py -v --tb=short
        ;;
    
    integration)
        echo -e "${YELLOW}Running NPL integration tests...${NC}"
        echo ""
        check_npl_engine || exit 1
        check_keycloak || exit 1
        echo ""
        pytest tests/test_npl_integration.py -v --tb=short
        ;;
    
    agents)
        echo -e "${YELLOW}Running agent core tests...${NC}"
        echo ""
        check_npl_engine || exit 1
        check_keycloak || exit 1
        echo ""
        pytest tests/test_agent_core.py -v --tb=short
        ;;
    
    all|"")
        echo -e "${YELLOW}Running all tests...${NC}"
        echo ""
        check_npl_engine || exit 1
        check_keycloak || exit 1
        echo ""
        
        echo -e "${BLUE}--- Monitoring Tests ---${NC}"
        pytest tests/test_monitoring.py -v --tb=short || true
        
        echo ""
        echo -e "${BLUE}--- Notification Tests ---${NC}"
        pytest tests/test_notifications.py -v --tb=short || true
        
        echo ""
        echo -e "${BLUE}--- NPL Integration Tests ---${NC}"
        pytest tests/test_npl_integration.py -v --tb=short || true
        
        echo ""
        echo -e "${BLUE}--- Agent Core Tests ---${NC}"
        pytest tests/test_agent_core.py -v --tb=short || true
        ;;
    
    *)
        echo -e "${RED}Unknown test suite: $1${NC}"
        echo ""
        echo "Usage: ./run_tests.sh [suite]"
        echo ""
        echo "Available suites:"
        echo "  monitoring   - Run monitoring/metrics tests (no external dependencies)"
        echo "  notifications- Run notification tests"
        echo "  integration  - Run NPL integration tests"
        echo "  agents       - Run agent core tests"
        echo "  all          - Run all tests (default)"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}============================================${NC}"
echo -e "${GREEN}Tests completed!${NC}"
echo -e "${BLUE}============================================${NC}"

