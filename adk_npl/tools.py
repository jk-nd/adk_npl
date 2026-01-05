"""
Dynamic tool generation from NPL Engine OpenAPI specs (Smart NPL Bridge).

This module implements the "Smart NPL Bridge" - a semantic layer that enriches
tools with goal-oriented descriptions, business rules, and workflow guidance.

Key Features:
- Parses NPL source files to extract workflow, states, and party permissions
- Infers goal-oriented descriptions from party names (e.g., 'seller' → 'selling')
- Generates self-documenting tools that guide agents toward correct usage
- No hardcoded mappings - everything is derived from NPL protocols
- Supports arbitrary party names and domain-specific protocols

Philosophy:
- Tools are NOT filtered by agent identity
- Instead, tools describe their purpose and typical use cases
- Agents self-select tools based on their objectives
- NPL enforces party bindings at runtime
"""

import logging
import inspect
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, get_type_hints
from google.adk.tools import FunctionTool

from .client import NPLClient
from .config import NPLConfig
from .discovery import NPLPackageDiscovery
from .protocol_memory import NPLProtocolMemory, create_memory_tools, auto_track_result
from .utils import (
    Cache,
    ToolDiscoveryError,
    parse_openapi_path,
    is_protocol_creation_path,
    is_action_execution_path
)

logger = logging.getLogger(__name__)

# Try to import diagram generator (optional - may not have NPL source files)
try:
    from .diagram_generator import generate_workflow_summary_for_protocol, NPLProtocolParser
    from .standards_registry import get_semantic_context
    HAS_SEMANTIC_BRIDGE = True
except ImportError:
    HAS_SEMANTIC_BRIDGE = False
    logger.warning("Semantic bridge components not available - summaries will be limited")


def create_typed_function(
    func_name: str,
    doc: str,
    param_specs: List[Dict[str, Any]],
    impl: Callable
) -> Callable:
    """
    Create a function with explicit typed parameters by generating code.
    
    This is necessary because ADK extracts parameter info from function signatures,
    and **kwargs doesn't expose parameter names/types to the LLM.
    
    Args:
        func_name: Name of the function
        doc: Docstring for the function
        param_specs: List of parameter specs with name, type, required, nullable
        impl: Implementation function to call
        
    Returns:
        A callable with explicit typed signature
    """
    # Sort params: required first, then optional (Python requires this order)
    sorted_specs = sorted(param_specs, key=lambda p: (
        not (p.get('required', True) and not p.get('nullable', False)),  # Required and non-nullable first
        p['name']  # Then alphabetically
    ))
    
    # Build parameter definitions
    params = []
    for p in sorted_specs:
        name = p['name']
        ptype = p.get('type', 'str')
        required = p.get('required', True)
        nullable = p.get('nullable', False)
        
        # Map to Python types
        type_str = {'str': 'str', 'float': 'float', 'int': 'int', 'bool': 'bool'}.get(ptype, 'str')
        
        if required and not nullable:
            params.append(f"{name}: {type_str}")
        else:
            params.append(f"{name}: {type_str} = None")
    
    param_str = ", ".join(params)
    
    # Build the function code
    code = f'''
def {func_name}({param_str}) -> dict:
    """
{doc}
    """
    kwargs = {{}}
'''
    
    for p in sorted_specs:
        name = p['name']
        nullable = p.get('nullable', False)
        code += f"    if {name} is not None:\n"
        code += f"        kwargs['{name}'] = {name}\n"
        if nullable:
            code += f"    else:\n"
            code += f"        kwargs['{name}'] = None\n"
    
    code += "    return _impl(**kwargs)\n"
    
    # Execute the code to create the function
    local_ns = {'_impl': impl}
    exec(code, local_ns)
    
    return local_ns[func_name]


def create_identity_tool(config: NPLConfig) -> FunctionTool:
    """Create a tool that returns the agent's own identity and party claims."""
    username = config.credentials.get("username", "unknown")
    
    # Extract org/dept from username pattern (e.g., purchasing_agent@acme-corp.com)
    email = username
    org = "Unknown"
    dept = "Unknown"
    
    if "@" in username:
        if "acme-corp" in username:
            org = "Acme Corp"
            dept = "Procurement" if "purchasing" in username else "Unknown"
        elif "supplier-inc" in username:
            org = "Supplier Inc"
            dept = "Sales" if "supplier" in username else "Unknown"
    elif "purchasing" in username:
        org = "Acme Corp"
        dept = "Procurement"
    elif "supplier" in username:
        org = "Supplier Inc"
        dept = "Sales"
    
    def get_my_identity() -> str:
        """
        Get your own identity and party claims for use in protocol bindings.
        
        CRITICAL: Call this BEFORE creating any multi-party protocol (Offer, PurchaseOrder).
        
        Returns:
            Your identity information with EXACT claim values to use in A2A messages
            and NPL protocol party bindings.
        """
        return f"""=== YOUR IDENTITY (use EXACTLY these values) ===

Organization: {org}
Department: {dept}

=== FOR A2A MESSAGES ===
When another agent asks for your identity, reply with:
"My identity: organization={org}, department={dept}"

=== FOR NPL PROTOCOL CREATION ===
When creating a multi-party protocol where YOU are a party, use:
{{"organization": "{org}", "department": "{dept}"}}

=== IMPORTANT ===
- These are YOUR claims from your JWT token
- The other party MUST provide THEIR claims via A2A before you can bind them
- NEVER invent or guess claims for other parties
"""
    
    return FunctionTool(get_my_identity)


class NPLToolGenerator:
    """
    Generates ADK tools from NPL Engine OpenAPI specs.
    
    Parses OpenAPI schemas to create Python functions with explicit
    typed parameters, making them self-documenting for LLMs.
    """
    
    # Error categories for structured error responses
    ERROR_PATTERNS = {
        "state_error": {
            "patterns": ["illegal protocol state", "current state is not", "not one of"],
            "retryable": True,
            "guidance": "The protocol is not in the correct state for this action. Query the protocol instance to check its current state, then wait and retry when the state allows this action."
        },
        "business_rule": {
            "patterns": ["business rule", "assertion failed", "require(", "validation"],
            "retryable": False,
            "guidance": "A business rule was violated. Check the error message for details and adjust your parameters to comply with the rule."
        },
        "not_found": {
            "patterns": ["no such", "not found", "does not exist", "404"],
            "retryable": False,
            "guidance": "The referenced item does not exist. Verify the ID is correct by querying for available instances."
        },
        "permission_denied": {
            "patterns": ["permission denied", "not authorized", "forbidden", "403"],
            "retryable": False,
            "guidance": "You don't have permission to perform this action. Check if you're using the correct party role."
        },
        "invalid_data": {
            "patterns": ["invalid", "malformed", "bad request", "400", "parse error"],
            "retryable": False,
            "guidance": "The data format is invalid. Check parameter types and formats - especially DateTime fields which must be in format '2006-01-02T15:04:05.999+01:00[Europe/Zurich]'."
        },
        "runtime_error": {
            "patterns": ["runtime error", "r13:", "r14:", "r15:"],
            "retryable": True,
            "guidance": "A runtime error occurred in the NPL protocol. This may be a state transition issue - query the protocol state and retry if appropriate."
        }
    }
    
    @classmethod
    def _create_structured_error(cls, error: Exception, action_name: str = "") -> Dict[str, Any]:
        """
        Create a structured error response that helps LLMs understand and handle errors.
        
        Categorizes the error and provides actionable guidance for recovery.
        
        Args:
            error: The exception that occurred
            action_name: The name of the action that failed (for context)
            
        Returns:
            Structured error dict with error_type, message, retryable, and guidance
        """
        error_str = str(error).lower()
        original_message = str(error)
        
        # Categorize the error
        error_type = "unknown_error"
        retryable = False
        guidance = "An unexpected error occurred. Check the error message for details."
        
        for category, config in cls.ERROR_PATTERNS.items():
            if any(pattern in error_str for pattern in config["patterns"]):
                error_type = category
                retryable = config["retryable"]
                guidance = config["guidance"]
                break
        
        return {
            "success": False,
            "error_type": error_type,
            "error": original_message,
            "retryable": retryable,
            "guidance": guidance,
            "action": action_name,
            "hint": "If retryable=True, check the protocol state and try again. If retryable=False, adjust your parameters."
        }

    def __init__(
        self,
        npl_client: NPLClient,
        cache_ttl: float = 300.0,
        protocol_memory: Optional[NPLProtocolMemory] = None,
        agent_id: str = "default"
    ):
        """
        Initialize tool generator.
        
        Args:
            npl_client: Authenticated NPL client
            cache_ttl: Cache TTL in seconds (default: 5 minutes)
            protocol_memory: Optional memory for tracking protocol instances
            agent_id: Agent identifier for memory scoping
        """
        self.npl_client = npl_client
        self.cache = Cache(default_ttl=cache_ttl)
        self._tools_cache: Optional[List[FunctionTool]] = None
        self._cache_time: float = 0.0
        self.agent_id = agent_id
        
        # Protocol memory for tracking instances across turns
        self.protocol_memory = protocol_memory or NPLProtocolMemory.get_instance(agent_id)
        
        # Try to find NPL source directory (for workflow diagram generation)
        self.npl_source_dir = self._find_npl_source_dir()
    
    def _find_npl_source_dir(self) -> Optional[Path]:
        """Try to find the NPL source directory relative to this package."""
        try:
            # Look for npl/src/main/npl-* directories
            current_file = Path(__file__)
            # adk_npl/tools.py -> adk_npl/ -> project root
            project_root = current_file.parent.parent
            npl_dir = project_root / "npl" / "src" / "main"
            if npl_dir.exists():
                return npl_dir
        except Exception:
            pass
        return None
    
    def _get_protocol_metadata(self, package: str, protocol_name: str) -> Optional[Dict]:
        """Get parsed metadata for a protocol if NPL source files are available."""
        if not self.npl_source_dir:
            return None
        
        try:
            # Try to match the protocol name to a filename in the package directory
            # Common mappings: PurchaseOrder -> purchase_order.npl, Offer -> offer.npl
            for npl_version_dir in self.npl_source_dir.glob("npl-*"):
                package_dir = npl_version_dir / package
                if not package_dir.exists():
                    continue
                
                # Look for files that might match
                possible_names = [
                    f"{protocol_name.lower()}.npl",
                    f"{''.join(['_' + c.lower() if c.isupper() else c for c in protocol_name]).lstrip('_')}.npl"
                ]
                
                for name in possible_names:
                    npl_file = package_dir / name
                    if npl_file.exists():
                        parser = NPLProtocolParser(npl_file)
                        return parser.parse()
        except Exception as e:
            logger.debug(f"Could not parse protocol metadata for {package}.{protocol_name}: {e}")
        
        return None
    
    def _get_dependent_protocols(self, package: str, protocol_name: str) -> List[Dict[str, str]]:
        """
        Find protocols in the same package that reference/import this protocol.
        
        Used for cross-protocol workflow guidance - when a protocol reaches a final
        state, this tells us what protocol(s) should be created next.
        
        Returns:
            List of dicts with 'protocol', 'reference_param', and 'suggestion'
        """
        if not self.npl_source_dir or not HAS_SEMANTIC_BRIDGE:
            return []
        
        dependents = []
        try:
            for npl_version_dir in self.npl_source_dir.glob("npl-*"):
                package_dir = npl_version_dir / package
                if not package_dir.exists():
                    continue
                
                for npl_file in package_dir.glob("*.npl"):
                    try:
                        parser = NPLProtocolParser(npl_file)
                        info = parser.parse()
                        other_protocol = info.get("protocol_name")
                        
                        # Skip self
                        if other_protocol == protocol_name:
                            continue
                        
                        # Check if this protocol references our protocol
                        # Look for: use commerce.Offer; or parameter type like acceptedOffer: Offer
                        content = npl_file.read_text()
                        
                        # Check imports
                        if f"use {package}.{protocol_name};" in content:
                            # Find parameter that uses this type
                            param_match = re.search(rf'(\w+)\s*:\s*{protocol_name}', content)
                            param_name = param_match.group(1) if param_match else protocol_name.lower()
                            
                            dependents.append({
                                "protocol": other_protocol,
                                "reference_param": param_name,
                                "suggestion": f"Create a {other_protocol} using npl_{package}_{other_protocol}_create() with this {protocol_name} as '{param_name}'"
                            })
                    except Exception as e:
                        logger.debug(f"Could not check {npl_file} for dependencies: {e}")
        except Exception as e:
            logger.debug(f"Could not scan for dependent protocols: {e}")
        
        return dependents
    
    def _get_workflow_summary(self, package: str, protocol_name: str) -> Optional[str]:
        """Get workflow summary for a protocol if NPL source files are available."""
        if not self.npl_source_dir or not HAS_SEMANTIC_BRIDGE:
            return None
        
        try:
            # Try to match the protocol name to a filename in the package directory
            # Common mappings: PurchaseOrder -> purchase_order.npl, Offer -> offer.npl
            for npl_version_dir in self.npl_source_dir.glob("npl-*"):
                package_dir = npl_version_dir / package
                if not package_dir.exists():
                    continue
                
                # Look for files that might match
                possible_names = [
                    f"{protocol_name.lower()}.npl",
                    f"{''.join(['_' + c.lower() if c.isupper() else c for c in protocol_name]).lstrip('_')}.npl"
                ]
                
                for name in possible_names:
                    npl_file = package_dir / name
                    if npl_file.exists():
                        return generate_workflow_summary_for_protocol(npl_file)
        except Exception as e:
            logger.debug(f"Could not generate workflow summary for {package}.{protocol_name}: {e}")
        
        return None

    def _generate_role_guidance(
        self, 
        protocol_name: str, 
        action_name: str, 
        parties: List[str],
        source_states: Optional[List[str]] = None,
        target_states: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate party role guidance for objective-based matching.
        
        Focus: Present party role clearly and let the LLM match objective to role.
        No hardcoded semantic dictionaries - trust LLM's language understanding.
        """
        sections = []
        
        # Party Role Section - Clear and simple
        if len(parties) == 1:
            party = parties[0]
            sections.append(f"### 🎯 PARTY ROLE: **{party}**")
            
            # Add Schema.org reference if available from metadata imports
            schema_org_url = self._get_schema_org_url(party, metadata)
            if schema_org_url:
                sections.append(f"Schema.org: {schema_org_url}")
            
            sections.append(f"\nThis action is performed by the party in the **{party}** role.")
            sections.append(f"\n**Before using this tool, ask yourself:** Does my objective align with the {party} role?")
        else:
            party_list = ', '.join(parties)
            sections.append(f"### 🎯 PARTY ROLES: **{party_list}**")
            sections.append(f"\nThis action can be performed by any party in these roles: **{party_list}**.")
            sections.append(f"\n**Before using this tool, ask yourself:** Does my objective align with any of these roles?")
        
        # Workflow Context - State requirements and transitions
        if source_states or target_states:
            sections.append("\n### 📋 WORKFLOW CONTEXT")
            if source_states:
                sections.append(f"**Valid from states:** `{', '.join(source_states)}`")
            if target_states:
                sections.append(f"**Transitions to:** `{', '.join(target_states)}`")
        
        return "\n".join(sections) + "\n"
    
    def _get_schema_org_url(self, party_name: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Extract Schema.org URL for a party role from metadata imports.
        
        When NPL adds JSON-LD support, this will come directly from the OpenAPI spec.
        For now, we check the imports for schema.org references.
        """
        if not metadata:
            return None
        
        # Check imports for schema.org references
        for imp in metadata.get('imports', []):
            if 'schema.org' in imp.lower():
                # Try to match party name in the import
                # e.g., "use @schema.org/seller" or "from schema.org import seller"
                if party_name.lower() in imp.lower():
                    # Return standard schema.org URL
                    return f"http://schema.org/{party_name.capitalize()}"
        
        # Fallback: if schema.org is imported, assume standard naming
        for imp in metadata.get('imports', []):
            if 'schema.org' in imp.lower():
                return f"http://schema.org/{party_name.capitalize()}"
        
        return None

    async def generate_tools(
        self,
        packages: Optional[List[str]] = None,
        force_refresh: bool = False
    ) -> List[FunctionTool]:
        """
        Generate ADK tools from NPL Engine OpenAPI specs.
        
        Args:
            packages: Optional list of packages to discover (None = auto-discover)
            force_refresh: If True, ignore cache and regenerate
            
        Returns:
            List of FunctionTool instances
            
        Raises:
            ToolDiscoveryError: If tool generation fails
        """
        # Check cache
        if not force_refresh and self._is_cache_valid():
            logger.info("Using cached tools")
            return self._tools_cache or []
        
        # Discover packages if not provided
        if packages is None:
            discovery = NPLPackageDiscovery(self.npl_client.base_url)
            packages = await discovery.discover_packages()
        
        logger.info(f"Generating tools for {len(packages)} package(s)")
        
        all_tools = []
        
        # Process each package
        for package in packages:
            try:
                tools = self._generate_tools_for_package(package)
                all_tools.extend(tools)
                logger.info(f"✅ Generated {len(tools)} tool(s) for package '{package}'")
            except Exception as e:
                logger.error(f"❌ Failed to generate tools for package '{package}': {e}")
                continue
        
        if not all_tools:
            raise ToolDiscoveryError("No tools generated from any package")
        
        # Add memory tools for protocol tracking
        memory_tools = create_memory_tools(self.agent_id)
        all_tools.extend(memory_tools)
        logger.info(f"✅ Added {len(memory_tools)} memory tool(s) for protocol tracking")
        
        # Cache results
        self._tools_cache = all_tools
        import time
        self._cache_time = time.time()
        
        logger.info(f"🎉 Generated {len(all_tools)} total tool(s)")
        return all_tools
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if self._tools_cache is None:
            return False
        import time
        age = time.time() - self._cache_time
        return age < 300.0  # Default 5 minutes
    
    def _generate_tools_for_package(self, package: str) -> List[FunctionTool]:
        """
        Generate tools for a specific package.
        
        Args:
            package: Package name
            
        Returns:
            List of FunctionTool instances
        """
        # Get OpenAPI spec (with caching)
        cache_key = f"openapi_spec_{package}"
        spec = self.cache.get(cache_key)
        
        if spec is None:
            spec = self.npl_client.get_openapi_spec(package)
            self.cache.set(cache_key, spec)
        
        if not spec or not spec.get("paths"):
            logger.warning(f"Package '{package}' has no paths in OpenAPI spec")
            return []
        
        # Store schemas for reference resolution
        self._schemas = spec.get("components", {}).get("schemas", {})
        
        tools = []
        
        # Track protocols that have create tools (for query tool generation)
        protocols_with_tools = set()
        
        # Process each path in the OpenAPI spec
        for path, methods in spec.get("paths", {}).items():
            if "post" not in methods:
                continue
            
            method_spec = methods["post"]
            
            if is_protocol_creation_path(path, package):
                protocol_name = parse_openapi_path(path, package)[0]
                func = self._create_schema_aware_create_function(
                    package, protocol_name, method_spec
                )
                tool = FunctionTool(func, require_confirmation=False)
                tools.append(tool)
                protocols_with_tools.add(protocol_name)
                
            elif is_action_execution_path(path, package):
                protocol_name, action_name = parse_openapi_path(path, package)
                func = self._create_action_execution_function(
                    package, protocol_name, action_name, method_spec
                )
                tool = FunctionTool(func, require_confirmation=False)
                tools.append(tool)
                protocols_with_tools.add(protocol_name)
        
        # Generate query tools for protocols that have create/action tools
        for protocol_name in protocols_with_tools:
            # Add get instance tool (for fetching specific instances by UUID)
            get_func = self._create_get_instance_function(package, protocol_name)
            tools.append(FunctionTool(get_func, require_confirmation=False))
            
            # Add next_actions tool (NPL-assisted state awareness)
            # This is the key tool for the "orient → decide → act → stop" pattern
            next_actions_func = self._create_next_actions_function(package, protocol_name)
            tools.append(FunctionTool(next_actions_func, require_confirmation=False))
            
            # TODO: Add GraphQL-based list tool for querying protocols by party
            # NPL has a GraphQL read model with JWT/claims authorization
            # For now, agents exchange protocol UUIDs via A2A messages
        
        return tools
    
    def _resolve_ref(self, ref: str) -> Dict[str, Any]:
        """Resolve a $ref to its schema definition."""
        if ref.startswith("#/components/schemas/"):
            schema_name = ref.split("/")[-1]
            return self._schemas.get(schema_name, {})
        return {}
    
    def _get_schema_for_path(self, method_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the request body schema from a method spec."""
        request_body = method_spec.get("requestBody", {})
        content = request_body.get("content", {})
        json_content = content.get("application/json", {})
        schema = json_content.get("schema", {})
        
        # Resolve $ref if present
        if "$ref" in schema:
            return self._resolve_ref(schema["$ref"])
        return schema
    
    def _flatten_schema(self, schema: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
        """
        Flatten a schema into a list of parameter definitions.
        
        Returns list of dicts with: name, type, required, nullable, description, enum
        
        Note: A field can be both "required" in OpenAPI (key must be present) and
        "nullable" (value can be null). For LLM tooling, we treat nullable fields
        as optional parameters with default None.
        """
        params = []
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        
        for prop_name, prop_def in properties.items():
            if prop_name == "@parties":
                # Handle parties separately
                continue
            
            full_name = f"{prefix}{prop_name}" if prefix else prop_name
            is_nullable = prop_def.get("nullable", False)
            
            # Resolve $ref
            if "$ref" in prop_def:
                ref_schema = self._resolve_ref(prop_def["$ref"])
                # Check if it's a nested object or a simple type/enum
                if ref_schema.get("type") == "object" and "properties" in ref_schema:
                    # Nested object - flatten with prefix
                    nested_params = self._flatten_schema(ref_schema, f"{full_name}_")
                    params.extend(nested_params)
                elif "enum" in ref_schema:
                    # Enum type
                    params.append({
                        "name": full_name,
                        "type": "str",
                        # If nullable, treat as optional for LLM (can pass None)
                        "required": prop_name in required and not is_nullable,
                        "nullable": is_nullable,
                        "enum": ref_schema.get("enum", []),
                        "description": f"One of: {', '.join(ref_schema.get('enum', []))}"
                    })
                else:
                    # Simple referenced type (like Product_Reference)
                    # Extract the referenced type name from the $ref
                    ref_name = prop_def["$ref"].split("/")[-1]  # e.g., "Product_Reference"
                    referenced_protocol = ref_name.replace("_Reference", "")  # e.g., "Product"
                    
                    params.append({
                        "name": full_name,
                        "type": "str",  # References are UUIDs
                        "required": prop_name in required and not is_nullable,
                        "nullable": is_nullable,
                        "description": f"UUID of an existing {referenced_protocol} protocol instance. You MUST create the {referenced_protocol} first using the `npl_*_{referenced_protocol}_create` tool, then use its @id (UUID) here. Do NOT use SKU, name, or any other identifier - only the UUID from the @id field.",
                        "format": "uuid"
                    })
            else:
                # Direct property
                param_type = self._map_openapi_type(prop_def)
                params.append({
                    "name": full_name,
                    "type": param_type,
                    # If nullable, treat as optional for LLM (can pass None)
                    "required": prop_name in required and not is_nullable,
                    "nullable": is_nullable,
                    "description": prop_def.get("description", ""),
                    "format": prop_def.get("format", ""),
                    "example": prop_def.get("example", "")
                })
        
        return params
    
    def _extract_parties(self, schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract party definitions from @parties in schema."""
        parties = []
        parties_ref = schema.get("properties", {}).get("@parties", {})
        
        if "$ref" in parties_ref:
            parties_schema = self._resolve_ref(parties_ref["$ref"])
            required_parties = set(parties_schema.get("required", []))
            
            for party_name in parties_schema.get("properties", {}).keys():
                parties.append({
                    "name": party_name,
                    "required": party_name in required_parties
                })
        
        return parties
    
    def _map_openapi_type(self, prop_def: Dict[str, Any]) -> str:
        """Map OpenAPI type to Python type hint string."""
        type_map = {
            "string": "str",
            "number": "float",
            "integer": "int",
            "boolean": "bool",
            "array": "list",
            "object": "dict"
        }
        openapi_type = prop_def.get("type", "string")
        return type_map.get(openapi_type, "str")
    
    def _get_format_examples(self) -> Dict[str, str]:
        """
        Get comprehensive format-to-example mapping for standard OpenAPI formats.
        
        This covers all standard OpenAPI 3.0 format types to provide examples
        when the Engine doesn't include them in the OpenAPI spec.
        
        Returns:
            Dictionary mapping format strings to example descriptions
        """
        return {
            # Date/Time formats (OpenAPI standard)
            'date': "Date string in ISO 8601 format. Example: '2025-01-15'",
            'date-time': "DateTime string in ISO 8601 format. Example: '2025-01-15T10:30:00Z'",
            'zoned-date-time': "DateTime string in zoned-date-time format (schema.org). Example: '2006-01-02T15:04:05.999+01:00[Europe/Zurich]'",
            
            # Identifier formats
            'uuid': "UUID string. Example: '550e8400-e29b-41d4-a716-446655440000'",
            'uri': "URI string. Example: 'http://localhost:12000/npl/commerce/Offer/123/publish'",
            'uri-reference': "URI reference string. Example: '/npl/commerce/Offer/123'",
            'email': "Email address. Example: 'user@example.com'",
            'hostname': "Hostname. Example: 'example.com'",
            'ipv4': "IPv4 address. Example: '192.168.1.1'",
            'ipv6': "IPv6 address. Example: '2001:0db8:85a3:0000:0000:8a2e:0370:7334'",
            
            # Numeric formats
            'int32': "32-bit signed integer. Example: 42",
            'int64': "64-bit signed integer. Example: 1234567890",
            'float': "Floating point number. Example: 3.14",
            'double': "Double precision floating point. Example: 3.14159265359",
            
            # Binary formats
            'byte': "Base64-encoded byte string. Example: 'SGVsbG8='",
            'binary': "Binary data (base64 encoded). Example: 'SGVsbG8gV29ybGQ='",
            
            # String formats
            'password': "Password string (sensitive, not displayed)",
        }
    
    def _infer_semantic_meaning(self, param_name: str, param_type: str) -> Optional[str]:
        """
        Infer semantic meaning from field name patterns.
        
        Uses common naming conventions to provide context when format/description
        are missing. This helps LLMs understand field purpose.
        
        Patterns are checked in order of specificity (most specific first).
        
        Args:
            param_name: Parameter name (may include prefix like 'priceSpecification_')
            param_type: Parameter type ('str', 'float', 'int', etc.)
            
        Returns:
            Inferred description or None
        """
        # Extract base name (remove prefixes like 'priceSpecification_')
        base_name = param_name.split('_')[-1].lower()
        
        # Check most specific patterns first
        
        # Unit/Duration patterns (check before generic 'time' patterns)
        if any(pattern in base_name for pattern in ['leadtime', 'duration', 'period', 'unitcode', 'unittext']):
            return "Unit of measurement or duration"
        
        # Currency patterns (check before generic 'price' patterns)
        if 'currency' in base_name and param_type == 'str':
            return "Currency code (e.g., 'USD', 'EUR')"
        
        # Code/Identifier patterns (check before generic 'number' patterns)
        if any(pattern in base_name for pattern in ['code', 'sku', 'gtin', 'barcode', 'ordernumber', 'tracking']):
            return "Code or identifier string"
        
        # Date/Time patterns (specific date/time fields)
        if any(pattern in base_name for pattern in ['date', 'validfrom', 'validthrough', 'expires', 'deadline', 'timestamp']):
            if param_type == 'str':
                return "Date or DateTime value"
            return "Date/time related value"
        
        # Generic time (only if not already matched above)
        if 'time' in base_name and 'leadtime' not in base_name:
            if param_type == 'str':
                return "Date or DateTime value"
            return "Time-related value"
        
        # Identifier patterns
        if any(pattern in base_name for pattern in ['id', 'uuid', 'reference', 'ref']):
            return "Identifier or reference value"
        
        # Quantity/Amount patterns (numeric)
        if param_type in ['float', 'int']:
            if any(pattern in base_name for pattern in ['quantity', 'amount', 'value', 'count', 'number', 'total', 'price', 'cost']):
                return "Numeric quantity or amount"
        
        # Currency/Money patterns (string or numeric)
        if any(pattern in base_name for pattern in ['price', 'cost', 'amount', 'total']):
            return "Monetary value"
        
        # Text/Description patterns
        if any(pattern in base_name for pattern in ['name', 'title', 'description', 'text', 'comment', 'note']):
            return "Text description or label"
        
        # Status/State patterns
        if any(pattern in base_name for pattern in ['status', 'state', 'condition']):
            return "Status or state value"
        
        # Organization/Party patterns
        if any(pattern in base_name for pattern in ['organization', 'org', 'company', 'department', 'party']):
            return "Organization or party identifier"
        
        return None
    
    def _build_param_description(self, param: Dict[str, Any]) -> str:
        """
        Build a comprehensive parameter description using OpenAPI metadata.
        
        Uses a systematic priority order to provide the best possible description:
        1. Enum values (if present) - most specific
        2. OpenAPI example (if present) - from Engine
        3. Format-based example (if format exists but no example) - standard formats
        4. Description from OpenAPI (if present) - from Engine
        5. Inferred semantic meaning (from field name patterns) - intelligent fallback
        6. Type-based hint (final fallback) - generic
        
        Args:
            param: Parameter dict with name, type, format, example, description, enum
            
        Returns:
            Description string for the parameter
        """
        param_name = param.get('name', '')
        param_type = param.get('type', 'str')
        enum_values = param.get('enum', [])
        example = param.get('example', '')
        format_type = param.get('format', '')
        description = param.get('description', '').strip()
        
        # Priority 1: Enum - show all values (most specific)
        if enum_values:
            return f"One of: {', '.join(enum_values)}"
        
        # Priority 2: Use OpenAPI example if available (from Engine)
        if example:
            if description:
                return f"{description}. Example: '{example}'"
            else:
                return f"Example: '{example}'"
        
        # Priority 3: Format-based examples (standard OpenAPI formats)
        if format_type:
            format_examples = self._get_format_examples()
            if format_type in format_examples:
                format_desc = format_examples[format_type]
                if description:
                    return f"{description}. {format_desc}"
                else:
                    return format_desc
        
        # Priority 4: Description from OpenAPI (from Engine, when available)
        if description:
            return description
        
        # Priority 5: Inferred semantic meaning (from field name patterns)
        inferred = self._infer_semantic_meaning(param_name, param_type)
        if inferred:
            return inferred
        
        # Priority 6: Type-based hint (final fallback)
        type_hints = {
            'str': "String value",
            'float': "Floating point number",
            'int': "Integer number",
            'bool': "Boolean value (true/false)",
            'list': "List of values",
            'dict': "Dictionary/object value",
        }
        return type_hints.get(param_type, "Value")
    
    def _create_schema_aware_create_function(
        self,
        package: str,
        protocol_name: str,
        method_spec: Dict[str, Any]
    ) -> Callable:
        """
        Create a function for protocol creation with explicit typed parameters.
        
        Parses the OpenAPI schema to generate a function with explicit
        parameters for each required and optional field.
        """
        summary = method_spec.get("summary", f"Create {protocol_name} instance")
        schema = self._get_schema_for_path(method_spec)
        
        # Flatten schema to get parameters
        params = self._flatten_schema(schema)
        parties = self._extract_parties(schema)
        
        # Build ALL parameter specs (parties + data fields)
        all_params = []
        
        # Add party parameters
        for party in parties:
            all_params.append({
                "name": f"{party['name']}_organization",
                "type": "str",
                "required": party.get('required', True),
                "nullable": False,
                "description": f"Organization name for {party['name']} party"
            })
            all_params.append({
                "name": f"{party['name']}_department",
                "type": "str",
                "required": party.get('required', True),
                "nullable": False,
                "description": f"Department name for {party['name']} party"
            })
        
        # Add data field parameters
        all_params.extend(params)
        
        # Build parameter documentation
        param_docs = []
        reference_fields = []  # Track fields that reference other protocols
        for p in all_params:
            req = "(required)" if p['required'] else "(optional)"
            desc = self._build_param_description(p)
            param_docs.append(f"{p['name']}: {p['type']} {req} - {desc}")
            
            # Check if this is a reference field (has format uuid and description mentions UUID)
            if p.get('format') == 'uuid' and 'UUID' in desc and 'protocol instance' in desc:
                # Extract the referenced protocol name from description
                # e.g., "UUID of an existing Product protocol instance"
                import re
                match = re.search(r'existing (\w+) protocol', desc)
                if match:
                    reference_fields.append({
                        'field': p['name'],
                        'protocol': match.group(1)
                    })
        
        func_name = f"npl_{package}_{protocol_name}_create"
        
        # Add guidance about party actions for multi-party protocols
        binding_warning = ""
        if len(parties) > 1:
            party_names = [p['name'] for p in parties]
            
            # Get metadata to understand which party can do what
            metadata = self._get_protocol_metadata(package, protocol_name)
            party_actions = {}
            if metadata:
                for perm in metadata.get('permissions', []):
                    for party in perm.get('parties', []):
                        if party not in party_actions:
                            party_actions[party] = []
                        party_actions[party].append(perm['action'])
            
            # Build action guidance for each party
            action_guidance = []
            for party in party_names:
                actions = party_actions.get(party, [])
                if actions:
                    action_guidance.append(f"- **{party}** can: {', '.join(actions)}")
                else:
                    action_guidance.append(f"- **{party}**: no specific actions found")
            
            # Determine which party typically creates this protocol
            # Key insight: The party who performs FIRST actions (from initial state) should create it
            # Even though all parties are bound to the protocol, only one initiates the workflow
            
            creator_party = None
            initial_state = None
            
            # Try to extract initial state from metadata (only if available)
            try:
                if metadata and isinstance(metadata, dict):
                    states = metadata.get('states', [])
                    if states and isinstance(states, list):
                        for state in states:
                            if isinstance(state, dict) and state.get('initial', False):
                                initial_state = state.get('name')
                                break
                
                # Find which party has actions FROM the initial state
                if initial_state and metadata and isinstance(metadata, dict):
                    permissions = metadata.get('permissions', [])
                    if permissions and isinstance(permissions, list):
                        for perm in permissions:
                            if not isinstance(perm, dict):
                                continue
                            # Check if this permission is valid from the initial state
                            perm_states = perm.get('states', [])
                            if not perm_states or initial_state in perm_states:
                                # This action can be performed from initial state
                                perm_parties = perm.get('parties', [])
                                if perm_parties and isinstance(perm_parties, list) and len(perm_parties) > 0:
                                    # Use the first party who can act from initial state
                                    creator_party = perm_parties[0]
                                    break
            except Exception as e:
                logger.debug(f"Could not extract initial state info for {protocol_name}: {e}")
            
            # Fallback: if no initial state logic, use party with most actions
            if not creator_party and party_actions:
                max_actions = 0
                for party in party_names:
                    actions = party_actions.get(party, [])
                    action_count = len(actions) if actions else 0
                    if action_count > max_actions:
                        max_actions = action_count
                        creator_party = party
            
            # Build WHO creates guidance with clear principle
            initial_state_note = f" (starts in '{initial_state}' state)" if initial_state else ""
            
            who_creates = f"""
### 🎯 WHO CREATES THIS PROTOCOL?

**Typically created by: {creator_party or 'any party'}**{initial_state_note}

This is a multi-party protocol involving: **{', '.join(party_names)}**

**CRITICAL PRINCIPLE:**
Even though ALL parties are bound to this protocol, **only ONE party should instantiate it**:
→ The party who needs to take the FIRST actions in the workflow sequence

**What can each party DO after creation?**
{chr(10).join(action_guidance)}

**⚠️ BEFORE CREATING, ASK YOURSELF:**
1. **Am I at the START of this protocol's workflow?**
   - If YES (you need to take first actions{f' from {initial_state} state' if initial_state else ''}) → YOU create it
   - If NO (you respond to someone else's actions) → WAIT for them to create and share UUID

2. **Do I need this protocol to EXIST to achieve my next goal?**
   - If YES → You're probably the initiator, create it
   - If NO → You're probably the responder, wait for it

**Example:**
- **{creator_party}** creates this protocol and takes initial actions
- Other parties WAIT for {creator_party} to send them the UUID via A2A
- Then they use npl_{package}_{protocol_name}_get(instance_id) to access and respond
- They perform THEIR actions on the EXISTING protocol instance

**Wrong:** Both parties trying to create their own instances → leads to confusion and duplicates
**Right:** One party creates, shares UUID, other parties respond to that instance
"""
            
            binding_warning = f"""{who_creates}

**⛔ MANDATORY: A2A IDENTITY EXCHANGE BEFORE CREATION**
You CANNOT use placeholder or invented claims like "PurchasingOrg" or "BuyerDept".
YOU MUST:
1. Call `get_my_identity` to get YOUR claims (organization, department)
2. Send an A2A message asking the other party: "What is your organization and department?"
3. WAIT for their reply with their EXACT claims
4. Use ONLY the claims they provided when creating this protocol

**Example A2A exchange:**
- You send: "I want to offer you a product. My identity: organization=Supplier Inc, department=Sales. What is YOUR organization and department?"
- They reply: "My identity: organization=Acme Corp, department=Procurement"
- NOW you can create the protocol using EXACTLY: seller={{organization=Supplier Inc, department=Sales}}, buyer={{organization=Acme Corp, department=Procurement}}

**If you don't have the other party's real claims, STOP and ask via A2A first.**
"""
        
        # Add Reference Workflow Warning if there are reference fields
        reference_warning = ""
        if reference_fields:
            ref_list = []
            for ref in reference_fields:
                ref_list.append(f"- **{ref['field']}**: Must be the UUID (@id) of an existing {ref['protocol']} instance. Create the {ref['protocol']} first using `npl_{package}_{ref['protocol']}_create`, then use its @id here.")
            
            # Build explicit sequence warning
            protocol_chain = " → ".join([ref['protocol'] for ref in reference_fields] + [protocol_name])
            
            reference_warning = f"""
### 🚨 CRITICAL: PROTOCOL DEPENDENCY SEQUENCE
This {protocol_name} CANNOT be created until prerequisites exist!

**REQUIRED SEQUENCE:**
{protocol_chain}

**Reference Fields:**
{chr(10).join(ref_list)}

**WRONG APPROACH:**
❌ Creating {protocol_name} first → NPL will REJECT (missing required fields)
❌ Using product name, SKU, or human-readable ID → NPL will REJECT

**CORRECT APPROACH:**
✅ 1. Check recall_my_protocols() to see if you already have the required protocols
✅ 2. If missing, create the prerequisite protocol(s) FIRST
✅ 3. Get the @id (UUID) from the creation result
✅ 4. Then create THIS protocol using that UUID in the {reference_fields[0]['field']} parameter

**Example:**
  result = npl_{package}_{reference_fields[0]['protocol']}_create(...)
  prerequisite_uuid = result['@id']  # e.g., "abc-123-def-456"
  npl_{package}_{protocol_name}_create({reference_fields[0]['field']}=prerequisite_uuid, ...)

If you try to skip this sequence, NPL will block you with a validation error.
"""

        # Get rich metadata if available
        metadata = self._get_protocol_metadata(package, protocol_name)
        semantic_info = ""
        workflow_summary = self._get_workflow_summary(package, protocol_name)
        
        if workflow_summary:
            semantic_info += f"### Workflow Summary\n{workflow_summary}\n\n"
        
        # Add party role guidance for protocol creation
        role_guidance = ""
        if parties:
            party_names = [p['name'] for p in parties]
            initiator = party_names[0]
            other_parties = party_names[1:]
            
            # Get Schema.org URL for initiator
            schema_org_url = self._get_schema_org_url(initiator, metadata)
            schema_line = f"\nSchema.org: {schema_org_url}" if schema_org_url else ""
            
            if len(party_names) == 1:
                role_guidance = f"""
### 🎯 PARTY ROLE: **{initiator}** (Creator){schema_line}

This protocol is created by the party in the **{initiator}** role.

**Before creating, ask yourself:** Does my objective align with the {initiator} role?
"""
            else:
                other_list = ', '.join(other_parties)
                role_guidance = f"""
### 🎯 PARTY ROLE: **{initiator}** (Typical Creator){schema_line}

This protocol is typically created by the **{initiator}**. 
Other parties involved: **{other_list}**

**Before creating, ask yourself:** 
- Does my objective align with the {initiator} role?
- If you are playing the role of {other_list}, you should typically WAIT for the {initiator} to create this, then use your party-specific actions.
"""
        
        if metadata:
            semantic_info += f"### Business Rules (Policy)\n"
            for req in metadata.get('global_requirements', []):
                semantic_info += f"- Rule: {req}\n"
            
            # Add Standards context (ISO, Schema.org, etc.)
            standards_context = []
            for imp in metadata.get('imports', []):
                standards_context.append(get_semantic_context(imp))
            
            if standards_context:
                semantic_info += f"\n### Industry Standards\n"
                semantic_info += "\n".join(standards_context) + "\n"

        doc = f"""╔══════════════════════════════════════════════════════════════════╗
║ ⚠️  READ ALL PARAMETER DESCRIPTIONS BEFORE CALLING THIS TOOL  ⚠️  ║
╚══════════════════════════════════════════════════════════════════╝

{summary}

{binding_warning}

{reference_warning}

{role_guidance}

{semantic_info}
Creates a new {protocol_name} protocol instance in the {package} package.

Args:
    {chr(10) + '    '.join(param_docs)}

Returns:
    On success: Protocol instance with @id and success=True
    On error: Structured error with error_type, retryable flag, and guidance

Error Handling:
    - If error_type='invalid_data': Check parameter formats (especially DateTime: '2006-01-02T15:04:05.999+01:00[Europe/Zurich]')
    - If error_type='business_rule': A validation rule failed - check the error message for details
    - If error_type='permission_denied': Verify the party credentials are correct
    - If retryable=True: Wait briefly and retry the action"""
        
        # Store params metadata for use in the closure
        params_meta = {p['name']: p for p in params}
        
        # Capture protocol memory for auto-tracking
        protocol_memory = self.protocol_memory
        
        # Create the implementation function
        def impl(**kwargs) -> Dict[str, Any]:
            """Dynamically generated protocol creation function."""
            try:
                # Build parties dict from *_organization and *_department params
                parties_dict = {}
                for party in parties:
                    org_key = f"{party['name']}_organization"
                    dept_key = f"{party['name']}_department"
                    org_val = kwargs.pop(org_key, None)
                    dept_val = kwargs.pop(dept_key, None)
                    if org_val and dept_val:
                        parties_dict[party['name']] = {
                            "claims": {
                                "organization": [org_val],
                                "department": [dept_val]
                            }
                        }
                
                # Unflatten kwargs into nested data structure
                data = {}
                
                # Include all nullable fields with None by default
                for param in params:
                    if param.get('nullable', False):
                        key = param['name']
                        value = kwargs.get(key, None)
                        parts = key.split('_')
                        current = data
                        for part in parts[:-1]:
                            if part not in current:
                                current[part] = {}
                            current = current[part]
                        current[parts[-1]] = value
                
                # Now add the rest
                for key, value in kwargs.items():
                    if value is None:
                        param_info = params_meta.get(key, {})
                        if not param_info.get('nullable', False):
                            continue
                        else:
                            continue
                    
                    parts = key.split('_')
                    current = data
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = value
                
                result = self.npl_client.create_protocol(
                    package=package,
                    protocol_name=protocol_name,
                    parties=parties_dict,
                    data=data
                )
                
                # #region agent log
                import json as _json_create, time as _time_create
                protocol_id = result.get("@id", "unknown") if isinstance(result, dict) else "unknown"
                with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
                    _f.write(_json_create.dumps({"location": "tools.py:create_result", "message": "Protocol created - UUID returned", "data": {"protocol": protocol_name, "uuid": protocol_id, "parties": list(parties_dict.keys())}, "hypothesisId": "H9", "timestamp": _time_create.time()}) + "\n")
                # #endregion
                
                # Add success indicator for clarity
                if isinstance(result, dict) and "@id" in result:
                    result["success"] = True
                    # Auto-track in protocol memory
                    auto_track_result(protocol_memory, protocol_name, result, role="owner")
                return result
            except Exception as e:
                return NPLToolGenerator._create_structured_error(e, f"{protocol_name}_create")
        
        # Create function with typed signature
        return create_typed_function(func_name, doc, all_params, impl)
    
    def _create_action_execution_function(
        self,
        package: str,
        protocol_name: str,
        action_name: str,
        method_spec: Dict[str, Any]
    ) -> Callable:
        """
        Create a function for action execution.
        
        Args:
            package: Package name
            protocol_name: Protocol name
            action_name: Action name
            method_spec: OpenAPI method specification
            
        Returns:
            Python function
        """
        summary = method_spec.get("summary", f"Execute {action_name}")
        
        # Get action parameters from schema
        schema = self._get_schema_for_path(method_spec)
        action_params = []
        if schema.get("properties"):
            action_params = self._flatten_schema(schema)
        
        # Build all parameters with explicit typing
        all_params = [
            {"name": "instance_id", "type": "str", "required": True, "nullable": False},
            {"name": "party", "type": "str", "required": False, "nullable": True}
        ]
        all_params.extend(action_params)
        
        # Build parameter docs for docstring
        param_docs = [
            "    instance_id: str (required) - The protocol instance UUID",
            "    party: str (optional) - The party role executing this action (e.g. 'seller', 'buyer')"
        ]
        for param in action_params:
            req = "(required)" if param['required'] else "(optional)"
            desc = self._build_param_description(param)
            param_docs.append(f"    {param['name']}: {param['type']} {req} - {desc}")
        
        func_name = f"npl_{package}_{protocol_name}_{action_name}"
        
        # Get workflow summary
        workflow_summary = self._get_workflow_summary(package, protocol_name)
        workflow_section = ""
        if workflow_summary:
            workflow_section = f"\n### Workflow Summary\n{workflow_summary}\n"
        
        # Get rich metadata if available
        metadata = self._get_protocol_metadata(package, protocol_name)
        action_rules = ""
        role_guidance = ""
        if metadata:
            logger.debug(f"Found metadata for {protocol_name}, checking {action_name}")
            # Find rules specific to this action
            for perm in metadata.get('permissions', []):
                if perm['action'] == action_name:
                    logger.debug(f"Matched permission for {action_name}")
                    
                    # Add comprehensive role/objective guidance with all three semantic layers
                    parties = perm.get('parties', [])
                    source_states = perm.get('source_states', [])
                    target_states = perm.get('target_states', [])
                    
                    if parties:
                        role_guidance = self._generate_role_guidance(
                            protocol_name, 
                            action_name, 
                            parties,
                            source_states=source_states,
                            target_states=target_states,
                            metadata=metadata
                        )
                    
                    if perm.get('requirements'):
                        action_rules += "\n### ⚠️ Business Rules\n"
                        for req in perm['requirements']:
                            action_rules += f"- {req}\n"

        doc = f"""╔══════════════════════════════════════════════════════════════════╗
║ ⚠️  READ ALL PARAMETER DESCRIPTIONS BEFORE CALLING THIS TOOL  ⚠️  ║
╚══════════════════════════════════════════════════════════════════╝

{summary}
{workflow_section}
{role_guidance}
{action_rules}
Executes the {action_name} action on a {protocol_name} protocol instance.

IMPORTANT: This action may only be valid in certain protocol states. If you receive a state_error,
query the protocol instance first to check its current state, then wait and retry when appropriate.

Args:
{chr(10).join(param_docs)}

Returns:
    On success: Action result with success=True
    On error: Structured error with error_type, retryable flag, and guidance

Error Handling:
    - If error_type='state_error' and retryable=True: The protocol is not in the correct state. 
      Query the instance to check its current state, wait, and retry when the state allows this action.
    - If error_type='business_rule': A validation rule failed - check the error message and adjust parameters.
    - If error_type='not_found': The instance_id is invalid - verify the ID by querying available instances.
    - If error_type='permission_denied': You may be using the wrong party role for this action.
"""
        
        # Capture protocol memory for auto-tracking
        protocol_memory = self.protocol_memory
        
        def impl(**kwargs) -> Dict[str, Any]:
            """Execute an action on a protocol instance."""
            try:
                instance_id = kwargs.pop("instance_id")
                party = kwargs.pop("party", None)
                result = self.npl_client.execute_action(
                    package=package,
                    protocol_name=protocol_name,
                    instance_id=instance_id,
                    action_name=action_name,
                    party=party,
                    params=kwargs
                )
                
                # #region agent log
                import json as _json_action, time as _time_action
                new_state = None
                if result is None:
                    new_state = "void_result"
                elif isinstance(result, dict):
                    new_state = result.get("@state") or result.get("state") or "unknown"
                with open("/Users/juerg/development/adk-demo/.cursor/debug.log", "a") as _f:
                    _f.write(_json_action.dumps({"location": "tools.py:action_executed", "message": "NPL action executed", "data": {"protocol": protocol_name, "action": action_name, "instance_id": instance_id, "party": party, "new_state": new_state}, "hypothesisId": "H12", "timestamp": _time_action.time()}) + "\n")
                # #endregion
                
                # Add success indicator for clarity
                if result is None:
                    # Update state in memory for void actions (state transitions)
                    protocol_memory.update_state(protocol_name, instance_id, action_name)
                    return {"success": True, "result": "Action completed successfully (void return)", "instance_id": instance_id}
                if isinstance(result, dict):
                    result["success"] = True
                    result["instance_id"] = instance_id
                    # Track state update if present
                    new_state = result.get("@state") or result.get("state")
                    if new_state:
                        protocol_memory.update_state(protocol_name, instance_id, new_state)
                return result
            except Exception as e:
                return NPLToolGenerator._create_structured_error(e, f"{protocol_name}_{action_name}")
        
        # Create function with typed signature so LLM can see all parameters
        return create_typed_function(func_name, doc, all_params, impl)
    
    def _create_get_instance_function(
        self,
        package: str,
        protocol_name: str
    ) -> Callable:
        """
        Create a function to get a specific protocol instance by ID.
        
        This is crucial for agents to check protocol state before attempting actions.
        """
        func_name = f"npl_{package}_{protocol_name}_get"
        
        doc = f"""Get a {protocol_name} protocol instance by ID.

Use this tool to check the current state of a protocol instance BEFORE attempting actions.
This is especially important when an action fails with a state_error - query the instance
to see its current state and determine when to retry.

Args:
    instance_id: str (required) - The protocol instance UUID

Returns:
    The protocol instance including:
    - @id: The instance UUID
    - @state: Current protocol state (e.g., 'created', 'published', 'accepted')
    - All protocol data fields
    
    On error: Structured error with error_type and guidance

Usage Pattern:
    1. Before actions: Query to verify the protocol is in the expected state
    2. After state_error: Query to see what state the protocol is actually in
    3. After retryable errors: Query, wait if needed, then retry when state allows
"""
        
        all_params = [
            {"name": "instance_id", "type": "str", "required": True, "nullable": False}
        ]
        
        def impl(**kwargs) -> Dict[str, Any]:
            """Get a protocol instance by ID."""
            try:
                instance_id = kwargs.get("instance_id")
                result = self.npl_client.get_instance(
                    package=package,
                    protocol_name=protocol_name,
                    instance_id=instance_id
                )
                if isinstance(result, dict):
                    result["success"] = True
                return result
            except Exception as e:
                return NPLToolGenerator._create_structured_error(e, f"{protocol_name}_get")
        
        return create_typed_function(func_name, doc, all_params, impl)
    
    def _create_next_actions_function(
        self,
        package: str,
        protocol_name: str
    ) -> Callable:
        """
        Create a tool that tells agents what actions are available based on current state.
        
        This is the "smart bridge" that combines:
        1. Current NPL state (from get_instance)
        2. Metadata about valid transitions (from NPL parser)
        3. Clear guidance on what to do next
        """
        func_name = f"npl_{package}_{protocol_name}_next_actions"
        metadata = self._get_protocol_metadata(package, protocol_name)
        
        doc = f"""Get available actions for a {protocol_name} instance based on its current state.

╔══════════════════════════════════════════════════════════════════╗
║  ORIENT: Use this tool to understand what you CAN do next!       ║
╚══════════════════════════════════════════════════════════════════╝

This tool queries NPL (the source of truth) for the protocol's current state,
then tells you exactly which actions are valid and who can perform them.

Args:
    instance_id: str (required) - The protocol instance UUID
    my_party: str (optional) - Your party role (e.g., 'seller', 'buyer') to filter actions

Returns:
    current_state: The protocol's current state (authoritative from NPL)
    available_actions: List of actions valid from this state
    For each action:
        - action: Action name
        - parties: Who can execute it
        - description: What this action does
        - target_state: Where it transitions to
        - tool_call: Exact tool call to execute

Usage Pattern (ORIENT → DECIDE → ACT → STOP):
    1. ORIENT: Call this tool to see what's possible
    2. DECIDE: Choose ONE action based on your goal
    3. ACT: Execute the tool_call from the action you chose
    4. STOP: Wait for the other party to respond
"""
        
        all_params = [
            {"name": "instance_id", "type": "str", "required": True, "nullable": False},
            {"name": "my_party", "type": "str", "required": False, "nullable": True}
        ]
        
        # Get permissions from metadata
        permissions = metadata.get('permissions', []) if metadata else []
        
        # Action descriptions for better hints
        action_descriptions = {
            # Offer actions
            "publish": "Make this offer visible to the buyer so they can review it",
            "accept": "Accept this offer and proceed with the transaction",
            "reject": "Decline this offer",
            "counter": "Propose different terms (price, quantity, etc.)",
            "withdraw": "Cancel this offer",
            "finalize": "Complete the transaction after acceptance",
            # Order actions
            "confirm": "Confirm the order and begin fulfillment",
            "ship": "Mark the order as shipped",
            "deliver": "Mark the order as delivered",
            "cancel": "Cancel this order",
            "approve": "Approve this order (for orders requiring approval)",
            # Product actions
            "activate": "Make this product available for offers",
            "deactivate": "Remove this product from availability",
            "update": "Modify product details",
        }
        
        def impl(**kwargs) -> Dict[str, Any]:
            """Get available actions based on current state."""
            try:
                instance_id = kwargs.get("instance_id")
                my_party = kwargs.get("my_party")
                
                
                # 1. Query NPL for current state (SOURCE OF TRUTH)
                instance = self.npl_client.get_instance(
                    package=package,
                    protocol_name=protocol_name,
                    instance_id=instance_id
                )
                
                if not isinstance(instance, dict):
                    return {"success": False, "error": "Could not retrieve instance"}
                
                current_state = instance.get("@state", "unknown")
                
                # 2. Find actions valid from this state
                available_actions = []
                all_parties_for_state = set()
                
                for perm in permissions:
                    source_states = perm.get('source_states', [])
                    
                    # Check if action is valid from current state
                    if current_state in source_states or not source_states:
                        parties = perm.get('parties', [])
                        all_parties_for_state.update(parties)
                        
                        # Filter by my_party if specified
                        if my_party and my_party.lower() not in [p.lower() for p in parties]:
                            continue
                        
                        action_name = perm['action']
                        target = perm.get('target_states', ['unchanged'])[0] if perm.get('target_states') else 'unchanged'
                        
                        # Build rich action info with description
                        action_info = {
                            "action": action_name,
                            "parties": parties,
                            "description": action_descriptions.get(action_name, f"Execute {action_name} action"),
                            "target_state": target if target != 'unchanged' else current_state,
                            "tool_call": f"npl_{package}_{protocol_name}_{action_name}(instance_id='{instance_id}', party='{parties[0] if parties else 'unknown'}')"
                        }
                        available_actions.append(action_info)
                
                # 3. Build helpful response with workflow context
                if not available_actions:
                    # Find what OTHER parties can do from this state
                    other_party_actions = []
                    for perm in permissions:
                        source_states = perm.get('source_states', [])
                        if current_state in source_states or not source_states:
                            parties = perm.get('parties', [])
                            action_name = perm['action']
                            target = perm.get('target_states', ['unchanged'])[0] if perm.get('target_states') else None
                            
                            # Only include actions for OTHER parties
                            if my_party and my_party.lower() not in [p.lower() for p in parties]:
                                other_party_actions.append({
                                    "action": action_name,
                                    "parties": parties,
                                    "leads_to": target,
                                    "description": action_descriptions.get(action_name, f"Execute {action_name}")
                                })
                    
                    # Find what actions YOU could take from the NEXT possible states
                    future_possibilities = []
                    possible_next_states = set()
                    for perm in permissions:
                        source_states = perm.get('source_states', [])
                        if current_state in source_states:
                            targets = perm.get('target_states', [])
                            possible_next_states.update(targets)
                    
                    for next_state in possible_next_states:
                        for perm in permissions:
                            if next_state in perm.get('source_states', []):
                                parties = perm.get('parties', [])
                                if not my_party or my_party.lower() in [p.lower() for p in parties]:
                                    future_possibilities.append({
                                        "when_state_is": next_state,
                                        "you_can": perm['action'],
                                        "description": action_descriptions.get(perm['action'], "")
                                    })
                    
                    # Build guidance message
                    waiting_for = []
                    if other_party_actions:
                        for action in other_party_actions[:3]:  # Limit to first 3
                            waiting_for.append(f"{', '.join(action['parties'])} can {action['action']}")
                    
                    # Check if this is a final state with dependent protocols
                    # Also check metadata for actual final state markers
                    is_final_state = not other_party_actions and not future_possibilities
                    
                    # Also check if NPL metadata says this is a final state
                    if metadata:
                        states = metadata.get('states', {})
                        if states.get(current_state) == 'final':
                            is_final_state = True
                    
                    next_protocol_suggestions = []
                    
                    if is_final_state:
                        # Look for protocols that depend on this one
                        dependents = self._get_dependent_protocols(package, protocol_name)
                        for dep in dependents:
                            next_protocol_suggestions.append({
                                "next_protocol": dep["protocol"],
                                "how_to_create": f"npl_{package}_{dep['protocol']}_create()",
                                "use_this_as": dep["reference_param"],
                                "suggestion": dep["suggestion"]
                            })
                    
                    result = {
                        "success": True,
                        "protocol": protocol_name,
                        "instance_id": instance_id,
                        "current_state": current_state,
                        "your_role": my_party or "not specified",
                        "available_actions": [],
                        "waiting_for": other_party_actions[:3] if other_party_actions else [],
                        "your_future_options": future_possibilities[:3] if future_possibilities else [],
                        "guidance": f"No actions available for you from state '{current_state}'.",
                        "what_needs_to_happen": waiting_for if waiting_for else ["This may be a final state."],
                    }
                    
                    # Add cross-protocol workflow guidance
                    if next_protocol_suggestions:
                        result["workflow_continues_with"] = next_protocol_suggestions
                        result["suggestion"] = (
                            f"This {protocol_name} is in final state '{current_state}'. "
                            f"The workflow continues by creating: {', '.join([s['next_protocol'] for s in next_protocol_suggestions])}. "
                            f"Use this instance's ID as the '{next_protocol_suggestions[0]['use_this_as']}' parameter."
                        )
                    else:
                        result["suggestion"] = "Wait for the other party to act, or use A2A to communicate with them."
                    
                    return result
                
                # Build guidance based on available actions
                action_choices = []
                for a in available_actions:
                    choice = f"• {a['action']}: {a['description']}"
                    if a['target_state'] != current_state:
                        choice += f" → moves to '{a['target_state']}'"
                    action_choices.append(choice)
                
                result = {
                    "success": True,
                    "protocol": protocol_name,
                    "instance_id": instance_id,
                    "current_state": current_state,
                    "your_role": my_party or "not specified",
                    "available_actions": available_actions,
                    "guidance": f"You have {len(available_actions)} option(s) from state '{current_state}':",
                    "your_choices": action_choices,
                    "next_step": "DECIDE which action aligns with your goal, then ACT by calling the tool_call."
                }
                return result
                
            except Exception as e:
                return NPLToolGenerator._create_structured_error(e, f"{protocol_name}_next_actions")
        
        return create_typed_function(func_name, doc, all_params, impl)
    
    def _create_list_instances_function(
        self,
        package: str,
        protocol_name: str
    ) -> Callable:
        """
        Create a function to list protocol instances with optional filtering.
        
        Helps agents discover existing instances and verify IDs.
        """
        func_name = f"npl_{package}_{protocol_name}_list"
        
        doc = f"""List {protocol_name} protocol instances.

Use this tool to discover existing protocol instances, verify IDs, or find instances
in a specific state. Useful when you need to find an instance to act on.

Args:
    page: int (optional) - Page number (default: 1)
    page_size: int (optional) - Number of results per page (default: 25, max: 100)
    state: str (optional) - Filter by protocol state (e.g., 'published', 'accepted')

Returns:
    List of protocol instances with @id, @state, and key data fields.
    
    On error: Structured error with error_type and guidance

Usage Pattern:
    1. Find instances: List all instances to discover what exists
    2. Filter by state: Use state parameter to find instances ready for specific actions
    3. Verify IDs: Confirm an instance exists before attempting actions
"""
        
        all_params = [
            {"name": "page", "type": "int", "required": False, "nullable": True},
            {"name": "page_size", "type": "int", "required": False, "nullable": True},
            {"name": "state", "type": "str", "required": False, "nullable": True}
        ]
        
        def impl(**kwargs) -> Dict[str, Any]:
            """List protocol instances."""
            try:
                page = kwargs.get("page", 1) or 1
                page_size = kwargs.get("page_size", 25) or 25
                state = kwargs.get("state")
                
                # Build filters for state if provided
                filters = {}
                if state:
                    filters["state"] = state
                
                result = self.npl_client.query_instances(
                    package=package,
                    protocol_name=protocol_name,
                    filters=filters if filters else None,
                    page=page - 1,  # query_instances expects 0-indexed
                    size=page_size
                )
                if isinstance(result, dict):
                    result["success"] = True
                elif isinstance(result, list):
                    result = {"success": True, "items": result, "count": len(result)}
                return result
            except Exception as e:
                return NPLToolGenerator._create_structured_error(e, f"{protocol_name}_list")
        
        return create_typed_function(func_name, doc, all_params, impl)
