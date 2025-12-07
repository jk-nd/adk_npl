# ADK Monitoring & Observability

ADK provides built-in tools for monitoring, debugging, and interacting with agents.

## 1. Web UI (Best for Interactive Testing)

The Web UI provides a visual interface to chat with agents.

### Start All Agents

```bash
cd /Users/juerg/development/adk-demo
./run_adk.sh
```

Open http://localhost:8000 and select an agent.

### What You'll See

- **Chat Interface**: Talk to your agent naturally
- **Tool Calls**: See when the agent uses tools (NPL or business tools)
- **Conversation History**: Review past interactions
- **Response Streaming**: Watch the agent think in real-time

## 2. Interactive CLI

Run individual agents with detailed logging:

```bash
source .venv/bin/activate
export PYTHONPATH=.

# Purchasing agent
adk run agents/purchasing

# Supplier agent
adk run agents/supplier
```

## 3. API Server

Start a REST API server for integration:

```bash
PYTHONPATH=. adk api_server agents/purchasing --port 8001
PYTHONPATH=. adk api_server agents/supplier --port 8002
```

### API Endpoints

```bash
# Send a message
curl -X POST http://localhost:8001/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a proposal for 100 widgets"}'

# Get conversation history
curl http://localhost:8001/history
```

## What Gets Monitored

### Tool Usage
Every tool call shows:
- Tool name and parameters
- Return value
- Execution time

**Example:**
```
🔧 Tool: npl_commerce_Product_create
   Input: {name: "Widget", category: "Industrial", ...}
   Output: {@id: "abc-123", @state: "active"}
   Duration: 234ms
```

### LLM Interactions
- Prompts sent to Gemini
- Token usage
- Latency

### Errors
- Stack traces
- Failed tool calls
- NPL protocol errors
- Authentication issues

## Observability Tips

1. **Use Web UI for demos** - Best visual experience
2. **Use CLI for debugging** - See detailed logs
3. **Use API for testing** - Automate scenarios
