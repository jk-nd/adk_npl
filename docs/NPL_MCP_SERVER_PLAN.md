# Generic NPL MCP Server - Enhancement Plan

## Vision

Create a **completely generic MCP server** that works with **any NPL application**, providing:
- Automatic discovery of all NPL packages
- Dynamic tool generation from OpenAPI specs
- Semantic enrichment (business rules, state transitions, party roles)
- Workflow-aware guidance (what actions are valid in current state)
- Standard MCP interface for any LLM client

## Design Principles

1. **Zero Configuration** - Auto-discover everything from NPL Engine
2. **No Domain Knowledge** - No hardcoded business logic or use-case assumptions
3. **Pure NPL Semantics** - All intelligence comes from NPL protocols themselves
4. **Standard MCP** - Works with Claude Desktop, VS Code, Cursor, any MCP client
5. **Separation of Concerns** - MCP server is stateless; NPL Engine is the source of truth

---

## Phase 1: Analysis & Requirements

### Current State (Noumena's Implementation)

```
┌─────────────────────────────────────────────────────────────┐
│                 Current MCP Server                          │
├─────────────────────────────────────────────────────────────┤
│ ✅ OpenAPI → MCP tools (via FastMCP.from_openapi)           │
│ ✅ OIDC authentication via Keycloak                         │
│ ✅ Token passthrough to NPL Engine                          │
│ ✅ Multiple transport options (stdio, SSE, HTTP)            │
│                                                             │
│ ❌ Single package only (hardcoded OPENAPI_URL)              │
│ ❌ No semantic enrichment of tool descriptions              │
│ ❌ No workflow awareness (next_actions)                     │
│ ❌ No business rule extraction                              │
│ ❌ No MCP Resources (only tools)                            │
│ ❌ No MCP Prompts                                           │
└─────────────────────────────────────────────────────────────┘
```

### Target State

```
┌─────────────────────────────────────────────────────────────┐
│                 Enhanced NPL MCP Server                     │
├─────────────────────────────────────────────────────────────┤
│ TOOLS (Actions)                                             │
│ ├── npl_list_packages()           - Discover all packages  │
│ ├── npl_{pkg}_{Proto}_create()    - Create protocol        │
│ ├── npl_{pkg}_{Proto}_{action}()  - Execute action         │
│ ├── npl_{pkg}_{Proto}_get()       - Get instance           │
│ ├── npl_{pkg}_{Proto}_query()     - Query instances        │
│ └── npl_{pkg}_{Proto}_next_actions() - Workflow guidance   │
│                                                             │
│ RESOURCES (Data)                                            │
│ ├── npl://packages                - List all packages      │
│ ├── npl://{pkg}/openapi           - OpenAPI spec           │
│ ├── npl://{pkg}/{proto}/workflow  - States, transitions    │
│ ├── npl://{pkg}/{proto}/rules     - Business rules         │
│ └── npl://{pkg}/{proto}/{id}      - Instance data          │
│                                                             │
│ PROMPTS (Templates)                                         │
│ └── npl_workflow_guide            - How to use NPL tools   │
└─────────────────────────────────────────────────────────────┘
```

### Requirements

| Req ID | Requirement | Priority |
|--------|-------------|----------|
| R1 | Auto-discover all NPL packages from Swagger UI | Must |
| R2 | Generate tools for ALL packages dynamically | Must |
| R3 | Extract workflow info from OpenAPI (states, actions) | Must |
| R4 | Provide `next_actions` tool for each protocol | Must |
| R5 | Enrich tool descriptions with semantic info | Should |
| R6 | Expose OpenAPI specs as MCP Resources | Should |
| R7 | Expose protocol instances as MCP Resources | Could |
| R8 | Support multiple authentication realms | Could |
| R9 | Provide workflow guide prompts | Could |

---

## Phase 2: Architecture

### Component Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        NPL MCP Server                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐    │
│  │  PackageDiscovery│   │  OpenAPIParser   │   │  SemanticExtractor│   │
│  │                  │   │                  │   │                   │    │
│  │  - Swagger UI    │   │  - Parse specs   │   │  - States         │    │
│  │  - List packages │   │  - Extract paths │   │  - Transitions    │    │
│  │                  │   │  - Extract schemas│   │  - Party roles   │    │
│  └────────┬─────────┘   └────────┬─────────┘   └────────┬──────────┘   │
│           │                      │                      │               │
│           └──────────────────────┼──────────────────────┘               │
│                                  ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      ToolGenerator                                │   │
│  │                                                                   │   │
│  │  - Generate create/action/get/query tools per protocol           │   │
│  │  - Generate next_actions tool per protocol                       │   │
│  │  - Enrich descriptions with semantic info                        │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                  │                                       │
│                                  ▼                                       │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                      FastMCP Server                               │   │
│  │                                                                   │   │
│  │  - Tools: npl_list_packages, npl_{pkg}_{proto}_*                 │   │
│  │  - Resources: npl://packages, npl://{pkg}/...                    │   │
│  │  - Auth: OIDC Proxy (Keycloak)                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                  │                                       │
└──────────────────────────────────┼───────────────────────────────────────┘
                                   ▼
                        ┌──────────────────┐
                        │   NPL Engine     │
                        │   (port 12000)   │
                        └──────────────────┘
```

### Data Flow

```
1. STARTUP
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ Swagger UI  │ ──► │ Discover    │ ──► │ For each    │
   │ /swagger-ui │     │ packages    │     │ package...  │
   └─────────────┘     └─────────────┘     └──────┬──────┘
                                                  │
   ┌─────────────┐     ┌─────────────┐            │
   │ Generate    │ ◄── │ Parse       │ ◄──────────┘
   │ MCP tools   │     │ OpenAPI     │
   └─────────────┘     └─────────────┘

2. RUNTIME (Tool Call)
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ MCP Client  │ ──► │ MCP Server  │ ──► │ NPL Engine  │
   │ (Claude)    │     │ (this)      │     │ API call    │
   └─────────────┘     └─────────────┘     └─────────────┘

3. WORKFLOW GUIDANCE (next_actions)
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ Get current │ ──► │ Match state │ ──► │ Return      │
   │ instance    │     │ to valid    │     │ available   │
   │ state       │     │ actions     │     │ actions     │
   └─────────────┘     └─────────────┘     └─────────────┘
```

---

## Phase 3: Core Implementation - Package Discovery

### 3.1 Package Discovery Module

```python
# npl_mcp/discovery.py

class PackageDiscovery:
    """Discover NPL packages from Engine's Swagger UI."""
    
    async def discover_packages(self) -> List[str]:
        """
        Parse Swagger UI HTML to extract package names.
        Returns: ["commerce", "insurance", "lending", ...]
        """
        
    async def get_openapi_spec(self, package: str) -> dict:
        """
        Fetch OpenAPI spec for a package.
        URL: /npl/{package}/-/openapi.json
        """
```

### 3.2 Multi-Package Tool Generation

Current (single package):
```python
mcp = FastMCP.from_openapi(openapi_spec=spec, ...)
```

Target (multiple packages):
```python
# Discover all packages
packages = await discovery.discover_packages()

# Generate tools for each
for pkg in packages:
    spec = await discovery.get_openapi_spec(pkg)
    tools = generate_tools_for_package(pkg, spec)
    mcp.add_tools(tools)
```

---

## Phase 4: Smart Tools - Workflow Awareness

### 4.1 OpenAPI Semantic Extraction

NPL OpenAPI specs contain semantic information we can extract:

```json
{
  "paths": {
    "/npl/commerce/Offer/": {
      "post": { "summary": "Create Offer" }
    },
    "/npl/commerce/Offer/{id}/publish": {
      "post": { 
        "summary": "Publish offer",
        "x-npl-parties": ["seller"],
        "x-npl-source-states": ["draft"],
        "x-npl-target-states": ["published"]
      }
    }
  }
}
```

**Note**: If `x-npl-*` extensions aren't present, we can infer from:
- Path patterns: `/{id}/{action}` = action on existing protocol
- Method names: "publish", "accept", "reject" suggest state transitions

### 4.2 `next_actions` Tool Design

```python
@mcp.tool()
async def npl_commerce_Offer_next_actions(
    instance_id: str,
    my_party: Optional[str] = None
) -> dict:
    """
    Get available actions for an Offer based on its current state.
    
    Args:
        instance_id: The protocol instance UUID
        my_party: Your party role (e.g., 'seller', 'buyer') to filter actions
    
    Returns:
        current_state: The protocol's current state
        available_actions: List of valid actions from this state
    """
    # 1. Get instance to find current state
    instance = await get_instance("commerce", "Offer", instance_id)
    current_state = instance["@state"]
    
    # 2. Look up valid actions for this state
    actions = get_valid_actions("commerce", "Offer", current_state, my_party)
    
    # 3. Return guidance
    return {
        "current_state": current_state,
        "available_actions": actions,
        "guidance": f"You can perform: {[a['action'] for a in actions]}"
    }
```

---

## Phase 5: Semantic Enrichment

### 5.1 Information Sources

| Source | What We Get | Availability |
|--------|-------------|--------------|
| OpenAPI spec | Endpoints, parameters, schemas | Always |
| OpenAPI extensions | `x-npl-states`, `x-npl-parties` | If NPL adds them |
| NPL source files | Full semantics (require, become, permission) | If available |
| Path/method patterns | Inferred state machine | Always |

### 5.2 Enrichment Strategy

**Tier 1: OpenAPI Only (Always Works)**
- Parse paths to identify protocols and actions
- Infer action types from path patterns
- Extract parameter schemas

**Tier 2: OpenAPI Extensions (If Available)**
- Use `x-npl-*` extensions for states, parties, rules
- NPL Engine could add these in future

**Tier 3: NPL Source Files (If Available)**
- Parse `.npl` files for full semantic extraction
- Business rules from `require()` statements
- State transitions from `become` statements

### 5.3 Tool Description Enrichment

Before:
```
Create a new Offer protocol instance.
```

After:
```
Create a new Offer protocol instance.

WORKFLOW: draft → published → accepted/rejected
PARTIES: seller (creates), buyer (responds)
BUSINESS RULES:
- Price must be positive
- Quantity must not exceed inventory

WHO CREATES: The seller creates Offers. Buyers wait for published offers.
```

---

## Phase 6: MCP Resources

### 6.1 Resource URIs

| URI Pattern | Returns |
|-------------|---------|
| `npl://packages` | List of all NPL packages |
| `npl://{pkg}/openapi` | OpenAPI spec for package |
| `npl://{pkg}/{proto}/workflow` | State machine, transitions, parties |
| `npl://{pkg}/{proto}/schema` | Input/output schemas |
| `npl://{pkg}/{proto}/{id}` | Protocol instance data |

### 6.2 Resource Implementation

```python
@mcp.resource("npl://packages")
async def list_packages() -> str:
    """List all available NPL packages."""
    packages = await discovery.discover_packages()
    return json.dumps({"packages": packages})

@mcp.resource("npl://{package}/openapi")
async def get_package_openapi(package: str) -> str:
    """Get OpenAPI spec for a package."""
    spec = await discovery.get_openapi_spec(package)
    return json.dumps(spec)

@mcp.resource("npl://{package}/{protocol}/workflow")
async def get_protocol_workflow(package: str, protocol: str) -> str:
    """Get workflow summary for a protocol."""
    workflow = await semantic_extractor.get_workflow(package, protocol)
    return json.dumps(workflow)
```

---

## Phase 7: Testing & Documentation

### 7.1 Test Scenarios

| Test | Description |
|------|-------------|
| Discovery | Server discovers all packages at startup |
| Tool Generation | Tools generated for all protocols |
| Tool Execution | CRUD operations work via MCP |
| next_actions | Returns valid actions for any state |
| Multi-Package | Works with commerce, insurance, any package |
| Auth Flow | OIDC flow works with Claude Desktop |

### 7.2 Documentation

- README with setup instructions
- Configuration reference
- Integration guide for Claude Desktop, VS Code, Cursor
- API reference for all tools and resources

---

## Implementation Order

```
Week 1: Phases 1-3
├── Fork/copy Noumena server
├── Add package discovery
├── Generate tools for all packages
└── Test with multiple packages

Week 2: Phase 4
├── Extract semantic info from OpenAPI
├── Implement next_actions tool
├── Test workflow awareness
└── Verify with real NPL protocols

Week 3: Phases 5-6
├── Add semantic enrichment
├── Implement MCP Resources
├── Add prompts (optional)
└── Integration testing

Week 4: Phase 7
├── Comprehensive testing
├── Documentation
├── Claude Desktop integration guide
└── Release
```

---

## Open Questions

1. **NPL Source Access**: Should the MCP server have access to `.npl` source files, or work purely from OpenAPI?
   - Recommendation: Start with OpenAPI-only, add NPL source as optional enhancement

2. **State Discovery**: How do we know valid states if not in OpenAPI extensions?
   - Recommendation: Infer from action path patterns + runtime observation

3. **Multi-Realm Auth**: Should we support different Keycloak realms per package?
   - Recommendation: Start with single realm, add multi-realm later

4. **Caching**: How long to cache OpenAPI specs?
   - Recommendation: Cache at startup, refresh on explicit command

---

## Success Criteria

The enhanced MCP server is successful when:

1. ✅ Works with ANY NPL application without code changes
2. ✅ Automatically discovers all packages
3. ✅ Generates semantically-rich tool descriptions
4. ✅ Provides workflow guidance via `next_actions`
5. ✅ Integrates with Claude Desktop, VS Code, Cursor
6. ✅ Handles authentication seamlessly
7. ✅ Is well-documented and easy to deploy
