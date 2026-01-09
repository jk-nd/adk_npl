# ADK-NPL Demo: Autonomous Agents with NPL Governance

A demonstration of AI agents conducting business transactions via the **A2A Protocol**, governed by **NPL (Noumena Protocol Language)** smart contracts.

## 🎯 What This Demo Shows

1. **Autonomous Agents**: Buyer and Supplier agents negotiate and transact independently
2. **NPL Governance**: Business rules, state transitions, and authorization enforced by the NPL Engine
3. **Smart NPL Bridge**: AI tools automatically enriched with contract semantics from NPL source code
4. **A2A Communication**: Agents communicate via the Agent-to-Agent protocol

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Human Interfaces                               │
│   [Buyer Chat] [Supplier Chat] [Approver Dashboard] [Activity Monitor]  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                          Chat API (8001)                                 │
│                    FastAPI + ADK Agent Runners                           │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Buyer Agent    │◄──►│ Supplier Agent  │    │ Activity API    │
│  (Purchasing)   │A2A │    (Sales)      │    │    (8002)       │
└────────┬────────┘    └────────┬────────┘    └─────────────────┘
         │                      │
         │    Smart NPL Bridge  │
         └──────────┬───────────┘
                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        NPL Engine (12000)                                │
│   Product → Offer → PurchaseOrder → Approval → Shipment                 │
│   [Multi-party State] [Business Rules] [Authorization]                   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│                        Keycloak (11000)                                  │
│                    Identity & Party Claims                               │
└─────────────────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- **Python 3.10+** (check with `python3 --version`; if you have 3.9 or earlier, install Python 3.10+ via Homebrew: `brew install python@3.12`)
- **Docker & Docker Compose** (Docker Desktop 4.41+ recommended)
- **Node.js 18+** (check with `node --version`; install via Homebrew if needed: `brew install node`)
- **Google API Key** for Gemini 2.0 (get from https://aistudio.google.com/app/apikey)

### Initial Setup

**1. Create `.env` file in project root:**
```bash
cat > .env << 'EOF'
# Google API Key (required for Chat API agents)
GOOGLE_API_KEY=your_actual_api_key_here

# Keycloak Admin Credentials
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=welcome

# NPL Engine Configuration (for general NPL client usage)
NPL_ENGINE_URL=http://localhost:12000
NPL_KEYCLOAK_URL=http://localhost:11000
NPL_KEYCLOAK_REALM=poc
NPL_USERNAME=test_agent
NPL_PASSWORD=welcome
NPL_KEYCLOAK_CLIENT_ID=poc

# Test User Password (for Keycloak provisioning)
SEED_TEST_USERS_PASSWORD=Welcome123
EOF
```

**Note:** The demo agents use `purchasing` and `supplier` realms (hardcoded in `chat_api/main.py`), which are automatically created by the provisioning script. The NPL config variables above are for general NPL client usage and can use any realm.

**2. Set up Python virtual environment:**
```bash
# Use Python 3.10+ (check version first)
python3 --version  # Should show 3.10, 3.11, or 3.12

# If you only have Python 3.9, install Python 3.12:
# brew install python@3.12
# Then use: python3.12 -m venv .venv

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

**3. Install frontend dependencies:**
```bash
cd frontend
npm install
cd ..
```

### 1. Start Infrastructure
```bash
./scripts/setup-fresh.sh
```
This starts: NPL Engine, Keycloak, PostgreSQL, and provisions Keycloak realms.

**Note:** The provisioning step creates the `purchasing` and `supplier` realms with users. This may take 2-3 minutes.

### 2. Start All Services (Recommended)

**One Command - Starts Everything:**
```bash
./start_demo.sh          # Start with existing database
./start_demo.sh --clean  # Reset NPL engine database (fresh session)
```

⚠️ **Use `--clean` for a truly fresh session**: This resets the NPL engine database, clearing all protocols from previous runs. Keycloak users remain unchanged. Without `--clean`, agents may reference old Product/Offer/PurchaseOrder instances.

This single script will:
- ✅ Check prerequisites (NPL Engine, Keycloak)
- ✅ Optionally reset NPL database (`--clean` flag)
- ✅ Start Activity API (port 8002)
- ✅ Start Frontend (port 5173)
- ✅ Start Chat API with A2A Agents (port 8001)
  - Buyer A2A: http://localhost:8010
  - Supplier A2A: http://localhost:8011

**All services run in the foreground** - you'll see terminal output from the Chat API. Press `Ctrl+C` to stop all services.

**Open the UI:** http://localhost:5173

### Troubleshooting

**Frontend redirects to Keycloak but doesn't load:**
- The frontend uses `localhost:11000` for Keycloak (browsers can't resolve Docker hostnames)
- If you had `/etc/hosts` entries mapping `keycloak` to `127.0.0.1` on another machine, you don't need them here
- The code automatically converts any `keycloak` hostname to `localhost` for browser compatibility

**Keycloak authentication fails:**
- Ensure Keycloak realms are provisioned: `docker-compose up -d keycloak-provisioning`
- Check realms exist: `curl http://localhost:11000/realms/purchasing`
- Verify Keycloak is running: `docker-compose ps keycloak`

**Python version errors:**
- Ensure you're using Python 3.10+: `python3 --version`
- If using Python 3.9, upgrade: `brew install python@3.12` then recreate venv with `python3.12 -m venv .venv`

**Missing dependencies:**
- Frontend: `cd frontend && npm install`
- Python: `pip install -r requirements.txt`

### Service Ports

| Service | Port | URL | Description |
|---------|------|-----|-------------|
| Frontend | 5173 | http://localhost:5173 | React dashboard UI |
| Chat API | 8001 | http://localhost:8001 | Main API with A2A agents |
| Activity API | 8002 | http://localhost:8002 | Activity logs & metrics |
| Buyer A2A | 8010 | http://localhost:8010 | Buyer agent A2A endpoint |
| Supplier A2A | 8011 | http://localhost:8011 | Supplier agent A2A endpoint |
| NPL Engine | 12000 | http://localhost:12000 | NPL protocol engine |
| Keycloak | 11000 | http://localhost:11000 | Identity provider |

### Alternative: Manual Start (Multiple Terminals)

If you prefer to start services individually:

**Terminal 1 - Activity API:**
```bash
cd activity_api && source ../.venv/bin/activate && ./run.sh
```

**Terminal 2 - Frontend:**
```bash
cd frontend && npm run dev
```

**Terminal 3 - Chat API & Agents:**
```bash
source .venv/bin/activate
cd chat_api && uvicorn main:app --host 0.0.0.0 --port 8001
```

**Production Build:**
The built frontend is served from `frontend/dist/`.

## 👥 User Personas

| Tab | Role | Actions |
|-----|------|---------|
| **Buyer** | Purchasing Agent | "Buy items on my shopping list" |
| **Supplier** | Sales Agent | "Register my products" |
| **Approvals** | Finance Approver | Approve high-value orders |
| **Activity** | Observer | Monitor all A2A and NPL activity |
| **Metrics** | Observer | View latency/call statistics |

## 📁 Project Structure

```
adk-demo/
├── adk_npl/                 # Core library: Smart NPL Bridge
│   ├── agent_factory.py     # Enterprise agent factory with ADK callbacks
│   ├── tools.py             # NPL tool generation with semantic enrichment
│   ├── client.py            # NPL Engine API client
│   └── ...
├── purchasing_agent/        # Buyer agent definition
├── supplier_agent/          # Supplier agent definition
├── chat_api/                # FastAPI server for human-agent interface
├── activity_api/            # Activity logging API server
├── frontend/                # React dashboard (TypeScript)
├── npl/                     # NPL protocol source files
│   └── src/main/npl-1.0/
│       └── commerce/        # Product, Offer, PurchaseOrder protocols
├── data/                    # Agent inventories
│   ├── buyer_shopping_list.json
│   └── supplier_inventory.json
├── tests/                   # Test suite (35 tests total)
├── scripts/                 # Setup and utility scripts
└── docs/                    # Additional documentation
```

## 🧪 Testing

```bash
# Run all tests
./run_tests.sh

# Or specific test suites
./run_tests.sh integration  # NPL integration tests
./run_tests.sh agents       # Agent core tests
./run_tests.sh monitoring   # Monitoring/metrics tests
./run_tests.sh notifications # Notification tests

# Or with pytest directly
pytest tests/ -v
```

### Test Coverage
- **12 NPL Integration Tests** (`test_npl_integration.py`): Authentication, OpenAPI, tool generation, protocol creation
- **5 Agent Core Tests** (`test_agent_core.py`): Agent creation, tool loading, execution
- **18 Monitoring Tests** (`test_monitoring.py`): Metrics collection, structured logging, health checks, telemetry
- **4 Notification Tests** (`test_notifications.py`): Routing logic, event parsing, payload structure, prompt structure

## 🔧 Key Components

### NPL-Assisted Active Agent Architecture

**The Problem**: After extensive development, we discovered that LLM agents cannot reliably infer workflow state from conversation context alone. Agents exhibited:
- **Infinite loops**: Repeatedly creating duplicate protocols
- **Amnesia**: Starting each turn as if conversation was new
- **State confusion**: Attempting invalid actions (e.g., "publish" already-published offers)
- **Ping-pong A2A**: Endless back-and-forth without progress
- **Tool spam**: 50+ tool calls per turn without meaningful results

**What We Tried** (and why it failed):
- ❌ **Prompt engineering**: LLMs don't reliably follow complex procedural instructions
- ❌ **Tool call limits**: Prevents runaway execution but doesn't guide behavior
- ❌ **Protocol memory**: Agents had memory but didn't use it consistently
- ❌ **ADK callbacks**: Good for enforcement, not for guidance
- ❌ **Simplified instructions**: Still requires LLM to infer "what action?" from context

**Root Cause**: LLMs are stateless, context gets noisy, and two agents inferring independently leads to inconsistent mental models. **NPL already has authoritative workflow state** - but agents weren't querying it.

**The Solution**: **NPL-Assisted Active Agents** - Agents query NPL for state rather than inferring it.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    ORIENT → DECIDE → ACT → STOP                             │
│                                                                              │
│  1. ORIENT: Query NPL for current state and valid actions                   │
│     └─→ npl_*_next_actions() → "You can: accept, reject, counter"           │
│     └─→ AUTHORITATIVE state from NPL Engine, not inferred from chat          │
│                                                                              │
│  2. DECIDE: Use judgment + A2A negotiation to choose action                 │
│     └─→ Agent DECIDES what's BEST (NPL tells what's POSSIBLE)               │
│     └─→ "Price is too high, I'll negotiate via A2A"                          │
│                                                                              │
│  3. ACT: Execute ONE action                                                 │
│     └─→ NPL validates and blocks if invalid                                 │
│     └─→ No more state confusion - NPL is the gatekeeper                     │
│                                                                              │
│  4. STOP: Let the other party respond                                       │
│     └─→ Turn-based prevents ping-pong                                        │
│     └─→ NPL notifications wake agent when it's their turn                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Principles:**
1. **Agents are ACTIVE** - They pursue goals, make decisions, negotiate via A2A
2. **NPL provides AWARENESS** - "What state are we in? What can I do?" (authoritative, not inferred)
3. **A2A enables CONVERGENCE** - Natural language negotiation preserved
4. **NPL prevents MISTAKES** - Invalid actions blocked automatically before execution

**Key Takeaways:**
- LLMs are not reliable state machines - give them authoritative state from external source
- Prompt engineering has limits - keep prompts simple: "Query state, decide, act, stop"
- External state machines are essential - NPL provides the "ground truth"
- A2A is for negotiation, not state management - use A2A for convergence, NPL for state
- Notifications enable reactive behavior - "It's your turn" is more reliable than "figure out whose turn it is"

See [`docs/WHY_AGENTS_FAILED.md`](docs/WHY_AGENTS_FAILED.md) for the complete journey and detailed analysis.

### Smart NPL Bridge
Unlike standard OpenAPI integrations, this project uses a "Smart Bridge" that:
- **Extracts business rules** from NPL `require` statements
- **Maps state transitions** from NPL `become` statements  
- **Provides state awareness** via `npl_*_next_actions()` tools
- **Routes notifications** to inform agents when state changes
- **Embeds semantics in tool docstrings** so agents understand contracts

### ADK Callbacks & Telemetry
Agents use Google ADK's callback system for:
- `before_tool_callback`: Enforce tool call limits (max 15/turn), record metrics
- `after_tool_callback`: Log tool completions, record latency metrics
- `on_tool_error_callback`: Categorize and handle NPL errors with guidance, record error metrics
- `on_model_error_callback`: Rate limit backoff with exponential backoff
- **OpenTelemetry Integration**: Automatic tracing of LLM calls, tool invocations, and agent reasoning

### Protocol Creation Principle
A key design principle emerged: **Only the party at the START of the workflow sequence should instantiate a protocol**.

For example, in the `Product → Offer → PurchaseOrder` sequence:
- **Supplier creates Product** (seller is the only party, can act from initial state)
- **Supplier creates Offer** (seller must publish from initial state, buyer joins later)
- **Buyer creates PurchaseOrder** (buyer initiates the order after accepting an offer)

This is enforced through:
1. **Dynamic Role Detection**: The Smart Bridge analyzes which party has permissions to act from the protocol's `initial state`
2. **Tool Docstring Guidance**: Each multi-party protocol creation tool includes "WHO CREATES THIS PROTOCOL?" guidance
3. **Workflow Sequence Awareness**: Tools document dependencies (e.g., "Offer requires Product", "PurchaseOrder requires Offer")

This prevents agents from creating protocols out of sequence or with incorrect party roles.

### NPL vs ADK: Complementary Roles
| Concern | NPL | ADK |
|---------|-----|-----|
| Workflow state | ✅ Authoritative source | ❌ Inferred (unreliable) |
| Valid actions | ✅ State-based rules | ❌ Guessed from context |
| Multi-party state | ✅ Shared, enforced | ❌ Agent-scoped |
| Business rules | ✅ Enforced by engine | ❌ In prompts only |
| Party authorization | ✅ Cryptographic claims | ❌ Trust-based |
| Agent reasoning | ❌ | ✅ LLM-powered |
| Negotiation | ❌ | ✅ A2A natural language |

## 📊 Monitoring & Observability

- **Activity Log**: Real-time trace of A2A messages, NPL calls, and agent thinking
- **Metrics Dashboard**: Comprehensive metrics including:
  - LLM API calls (by agent, latency)
  - Agent tool calls (by agent, by tool, success rate)
  - A2A messages (sent/received, roundtrip time, success rate)
  - NPL notifications (received/processed, by type, processing time)
  - NPL API calls (by action, latency)
  - Error tracking
- **ADK Telemetry**: OpenTelemetry integration for LLM calls, tool invocations, and agent reasoning
- **Theme Toggle**: Dark/Light mode support

### UI Controls

- **↻ Restart Button**: Restarts the Chat API server (reloads agents, clears history)
- **⏹ Stop Button**: Gracefully shuts down the Chat API server

## 📚 Documentation

- **`docs/WHY_AGENTS_FAILED.md`** - **Start here**: The journey from failing agents to NPL-assisted architecture
- **`docs/DEMO_RUN_REPORT.md`** - Comprehensive analysis of a demo run with metrics
- `docs/AGENTS.md` - Agent architecture and design principles
- `docs/MONITORING.md` - Observability, metrics, and telemetry
- `docs/A2A_COMMUNICATION.md` - Agent-to-Agent protocol details
- `docs/MOTIVATION.md` - Project motivation and goals
- `adk_npl/README.md` - Smart Bridge library documentation

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.
