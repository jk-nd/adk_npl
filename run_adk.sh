#!/bin/bash

# Activate virtual environment
source .venv/bin/activate

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Add current directory to PYTHONPATH to ensure modules are found
export PYTHONPATH=$PYTHONPATH:.

# Run ADK Web UI
echo "🚀 Starting ADK Web UI..."
echo "   Access at: http://127.0.0.1:8000"
echo "   Press Ctrl+C to stop"
echo ""

adk web agents --port 8000
