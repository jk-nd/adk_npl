#!/bin/bash
# Test script to verify fresh build and demo workflow
# Run this before making a pull request

set -e

echo "🧪 Testing Fresh Build and Demo Workflow"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
echo "1️⃣  Checking prerequisites..."

# Check Python
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "   ✅ Python: $PYTHON_VERSION"
else
    echo -e "   ${RED}❌ Python 3 not found${NC}"
    exit 1
fi

# Check Docker
if command -v docker &> /dev/null && docker ps &> /dev/null; then
    echo "   ✅ Docker: $(docker --version | cut -d' ' -f3 | tr -d ',')"
else
    echo -e "   ${RED}❌ Docker not found or not running${NC}"
    exit 1
fi

# Check Docker Compose
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    echo "   ✅ Docker Compose: available"
else
    echo -e "   ${RED}❌ Docker Compose not found${NC}"
    exit 1
fi

# Check Node.js (for frontend)
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo "   ✅ Node.js: $NODE_VERSION"
else
    echo -e "   ${YELLOW}⚠️  Node.js not found (needed for frontend)${NC}"
fi

# Check npm (for frontend)
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    echo "   ✅ npm: $NPM_VERSION"
else
    echo -e "   ${YELLOW}⚠️  npm not found (needed for frontend)${NC}"
fi

# Check .env file
echo ""
echo "2️⃣  Checking environment configuration..."
if [ -f .env ]; then
    if grep -q "GOOGLE_API_KEY" .env && ! grep -q "GOOGLE_API_KEY=$" .env && ! grep -q "GOOGLE_API_KEY=\"\"" .env; then
        echo "   ✅ .env file exists with GOOGLE_API_KEY"
    else
        echo -e "   ${YELLOW}⚠️  .env file exists but GOOGLE_API_KEY may not be set${NC}"
        echo "      (Demo will fail if API key is missing)"
    fi
else
    echo -e "   ${YELLOW}⚠️  .env file not found${NC}"
    echo "      Run: cp .env.example .env"
    echo "      Then add your GOOGLE_API_KEY"
fi

# Check Python virtual environment
echo ""
echo "3️⃣  Checking Python environment..."
if [ -d .venv ]; then
    echo "   ✅ Virtual environment exists"
    if [ -f .venv/bin/activate ]; then
        echo "   ✅ Virtual environment is valid"
    fi
else
    echo -e "   ${YELLOW}⚠️  Virtual environment not found${NC}"
    echo "      Run: python3 -m venv .venv"
    echo "      Then: source .venv/bin/activate"
    echo "      Then: pip install -r adk_npl/requirements.txt"
fi

# Check if services are running
echo ""
echo "4️⃣  Checking Docker services..."
if docker-compose ps 2>/dev/null | grep -q "Up" || docker compose ps 2>/dev/null | grep -q "Up"; then
    echo "   ✅ Some Docker services are running"
    echo -n "   Checking NPL Engine: "
    if curl -s http://localhost:12000/actuator/health 2>/dev/null | grep -q '"status":"UP"'; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️  Not responding${NC}"
    fi
    
    echo -n "   Checking Keycloak: "
    if curl -s http://localhost:11000/realms/purchasing 2>/dev/null | grep -q '"realm":"purchasing"'; then
        echo -e "${GREEN}✅${NC}"
    else
        echo -e "${YELLOW}⚠️  Not responding${NC}"
    fi
else
    echo -e "   ${YELLOW}⚠️  No Docker services running${NC}"
    echo "      Run: ./scripts/setup-fresh.sh"
fi

# Test demo script (dry run - check imports)
echo ""
echo "5️⃣  Testing demo script (syntax check)..."
if python3 -m py_compile demo_approval_workflow.py 2>/dev/null; then
    echo "   ✅ demo_approval_workflow.py syntax is valid"
else
    echo -e "   ${RED}❌ demo_approval_workflow.py has syntax errors${NC}"
    exit 1
fi

# Check if required modules can be imported
echo ""
echo "6️⃣  Testing Python imports..."
if [ -d .venv ]; then
    source .venv/bin/activate
    if python3 -c "from adk_npl import NPLConfig, NPLClient; from adk_npl.auth import KeycloakAuth" 2>/dev/null; then
        echo "   ✅ Required modules can be imported"
    else
        echo -e "   ${YELLOW}⚠️  Some modules cannot be imported${NC}"
        echo "      Run: pip install -r adk_npl/requirements.txt"
    fi
    deactivate 2>/dev/null || true
else
    echo -e "   ${YELLOW}⚠️  Skipping (no virtual environment)${NC}"
fi

# Summary
echo ""
echo "=========================================="
echo "📋 Test Summary"
echo "=========================================="
echo ""
echo "To run a complete fresh build test:"
echo ""
echo "1. Clean start:"
echo "   docker-compose down -v"
echo "   ./scripts/setup-fresh.sh"
echo ""
echo "2. Run demo:"
echo "   source .venv/bin/activate"
echo "   export PYTHONPATH=\$PYTHONPATH:."
echo "   python demo_approval_workflow.py"
echo ""
echo "3. Test frontend (optional):"
echo "   ./setup_hosts.sh"
echo "   cd frontend && npm install && npm run dev"
echo ""
echo "=========================================="

