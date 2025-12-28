#!/bin/bash
# Start the Activity Feed API server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Starting Activity Feed API..."
echo "   URL: http://localhost:8002"
echo "   Docs: http://localhost:8002/docs"
echo ""

# Check if running in virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "⚠️  Warning: Not running in a virtual environment"
    echo "   Recommended: source ../.venv/bin/activate"
    echo ""
fi

python3 main.py

