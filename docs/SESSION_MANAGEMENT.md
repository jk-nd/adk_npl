# Session Management and Data Persistence

## The Problem

When restarting the demo agents, they were referencing **products and offers from previous sessions**. This caused confusion and incorrect workflows.

### Root Causes

1. **Protocol Memory Not Cleared**: `NPLProtocolMemory` uses a class-level singleton pattern (`_instances` dict) that persists across agent restarts. When agents restarted, they retained references to old protocol instances.

2. **NPL Database Persistence**: The NPL engine database (PostgreSQL) persists across restarts. Agents querying the database would find old protocols from previous sessions.

### Impact

- Agents created offers referencing products from earlier sessions
- Protocol state became inconsistent
- Workflow sequences broke because agents operated on stale data
- ~45 GET requests per session retrieved old protocols

## The Solution

### 1. Clear Protocol Memory on Restart

**File: `chat_api/main.py`**

The `restart_session` endpoint now explicitly clears the protocol memory singleton:

```python
# Clear protocol memory (singleton instances that persist across restarts)
from adk_npl.protocol_memory import NPLProtocolMemory
NPLProtocolMemory.clear_all()

logger.info("✅ Agent state and protocol memory cleared")
```

This ensures agents start with a clean memory slate, forgetting all previous protocol references.

### 2. Database Reset Option

**File: `start_demo.sh`**

Added a `--clean` flag to reset the NPL engine database before starting:

```bash
./start_demo.sh --clean
```

This performs:
- `docker-compose stop engine engine-db` (stop NPL engine and its database)
- `docker volume rm -f adk-demo_engine-db` (force remove engine database volume)
- `docker-compose up -d engine-db` (restart database with fresh volume)
- `docker-compose up -d engine` (restart engine connected to clean database)
- Waits for engine health check

**Note**: Keycloak and its database are preserved - only the NPL engine database is reset. User credentials and realms remain intact. This is much faster than a full infrastructure reset.

**Technical Detail**: The `engine-db` service now uses a named Docker volume (`engine-db:/var/lib/postgresql/data`) instead of an anonymous volume. This ensures the `--clean` flag can reliably target and remove the correct database.

### Usage

**For quick iteration (keep existing protocols):**
```bash
./start_demo.sh
```

**For a fresh session (recommended for testing):**
```bash
./start_demo.sh --clean
```

## Why This Matters

**NPL is designed for production persistence**. In a real-world system:
- Products, offers, and orders should persist across restarts
- Agents should be able to resume interrupted workflows
- State is deliberately durable for audit and compliance

**But for demos and testing**, this persistence can cause confusion when:
- Testing new agent behaviors
- Validating workflow changes
- Debugging specific scenarios

The `--clean` flag provides the best of both worlds:
- Default behavior preserves state (production-like)
- Clean restarts available for testing and demos
- Fast reset (only NPL engine, not Keycloak)

## Architecture Implications

This issue highlighted an important architectural principle:

**Agents have two types of memory:**

1. **Agent Memory** (cleared on restart):
   - Conversation history
   - Message queues
   - Notification deduplication
   - A2A connection state

2. **Protocol Memory** (singleton, persists across restarts):
   - NPL protocol instance tracking
   - Protocol IDs and states
   - Role relationships

For true session isolation, both must be cleared. The UI "Restart" button now does this correctly.

## Related Files

- `chat_api/main.py` - REST API with session management
- `start_demo.sh` - Main startup script with `--clean` option
- `adk_npl/protocol_memory.py` - Protocol memory singleton
- `scripts/setup-fresh.sh` - Full infrastructure reset (includes Keycloak + NPL)

