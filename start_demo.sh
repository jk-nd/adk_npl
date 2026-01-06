#!/bin/bash
# Start the complete ADK-NPL demo with all services
# This script runs everything in the foreground with terminal output
#
# Usage: 
#   ./start_demo.sh          # Start with existing database
#   ./start_demo.sh --clean  # Reset NPL database before starting

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Parse arguments
CLEAN_DB=false
if [ "$1" = "--clean" ]; then
    CLEAN_DB=true
fi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}🚀 Starting ADK-NPL Demo - Complete System${NC}"
if [ "$CLEAN_DB" = true ]; then
    echo -e "${YELLOW}   (With clean database reset)${NC}"
fi
echo -e "${BLUE}============================================================${NC}"
echo ""

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Virtual environment not found!${NC}"
    echo "   Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if NPL engine is running
echo -e "${YELLOW}📡 Checking NPL Engine...${NC}"
if ! curl -s http://localhost:12000/health > /dev/null 2>&1; then
    echo -e "${RED}❌ NPL Engine not running on http://localhost:12000${NC}"
    echo "   Please start the NPL engine first:"
    echo "   cd npl && docker compose up -d"
    exit 1
fi
echo -e "${GREEN}✅ NPL Engine is running${NC}"

# Reset NPL engine database if --clean flag is set
if [ "$CLEAN_DB" = true ]; then
    echo ""
    echo -e "${YELLOW}🗑️  Resetting NPL Engine database (keeping Keycloak)...${NC}"
    
    # Stop engine and database
    echo -e "${YELLOW}   Stopping engine and database...${NC}"
    docker-compose stop engine engine-db
    
    # Remove the named volume
    echo -e "${YELLOW}   Removing engine database volume...${NC}"
    docker volume rm -f adk-demo_engine-db 2>/dev/null || true
    
    # Restart database and engine with fresh volume
    echo -e "${YELLOW}   Starting engine-db and engine with clean database...${NC}"
    docker-compose up -d engine-db
    sleep 5  # Give DB time to initialize
    docker-compose up -d engine
    
    # Wait for health check
    echo -n "   Waiting for NPL Engine"
    for i in {1..60}; do
        if curl -s http://localhost:12000/health > /dev/null 2>&1; then
            echo ""
            echo -e "${GREEN}✅ NPL Engine restarted with clean database${NC}"
            break
        fi
        if [ $((i % 5)) -eq 0 ]; then
            echo -n "."
        fi
        sleep 1
    done
    
    echo ""
fi
echo ""

# Check if Keycloak is running
echo -e "${YELLOW}🔐 Checking Keycloak...${NC}"
if ! curl -s http://localhost:11000/health > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Keycloak not running (may be optional)${NC}"
else
    echo -e "${GREEN}✅ Keycloak is running${NC}"
fi
echo ""

# Create logs directory
mkdir -p logs

# Note: Activity logs are kept for historical record
# Each session creates a new activity_TIMESTAMP.json file
echo -e "${BLUE}📝 Activity logs will be created in logs/ directory${NC}"
echo ""

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down services...${NC}"
    pkill -f "activity_api/main.py" 2>/dev/null || true
    pkill -f "chat_api/main.py" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    echo -e "${GREEN}✅ Cleanup complete${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start Activity API in background (but capture output)
echo -e "${BLUE}📊 Starting Activity API (port 8002)...${NC}"
cd activity_api
python3 main.py > ../logs/activity_api.log 2>&1 &
ACTIVITY_API_PID=$!
cd ..
sleep 2

# Check if Activity API started
if ! curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "${RED}❌ Activity API failed to start${NC}"
    tail -20 logs/activity_api.log
    exit 1
fi
echo -e "${GREEN}✅ Activity API running on http://localhost:8002${NC}"
echo ""

# Start Frontend in background (but capture output)
echo -e "${BLUE}🎨 Starting Frontend (port 5173)...${NC}"
cd frontend
npm run dev > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
sleep 3

# Check if Frontend started
if ! curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Frontend may still be starting...${NC}"
else
    echo -e "${GREEN}✅ Frontend running on http://localhost:5173${NC}"
fi
echo ""

# Start Chat API (main demo) in foreground - this is the main process
echo -e "${BLUE}🤖 Starting Chat API with A2A Agents (port 8001)...${NC}"
echo -e "${BLUE}   Buyer A2A:    http://localhost:8010${NC}"
echo -e "${BLUE}   Supplier A2A: http://localhost:8011${NC}"
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}✅ All services started!${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo -e "${YELLOW}📱 Open your browser:${NC}"
echo -e "   Frontend:    http://localhost:5173"
echo -e "   Activity API: http://localhost:8002"
echo -e "   Chat API:    http://localhost:8001"
echo ""
echo -e "${YELLOW}📝 Logs:${NC}"
echo -e "   Activity API: logs/activity_api.log"
echo -e "   Frontend:     logs/frontend.log"
echo -e "   Chat API:     (output below)"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""
echo -e "${BLUE}============================================================${NC}"
echo ""

# Run the main chat API in foreground (this blocks)
cd chat_api && uvicorn main:app --host 0.0.0.0 --port 8001

