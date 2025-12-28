"""
Dynamic tool generation from NPL Engine OpenAPI specs.

Generates Python functions with explicit typed parameters from OpenAPI schemas,
making them self-documenting for LLM consumption.
"""

import logging
import inspect
from typing import List, Dict, Any, Optional, Callable, get_type_hints
from google.adk.tools import FunctionTool

from .client import NPLClient
from .discovery import NPLPackageDiscovery
from .utils import (
    Cache,
    ToolDiscoveryError,
    parse_openapi_path,
    is_protocol_creation_path,
    is_action_execution_path
)

logger = logging.getLogger(__name__)


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


class NPLToolGenerator:
    """
    Generates ADK tools from NPL Engine OpenAPI specs.
    
    Parses OpenAPI schemas to create Python functions with explicit
    typed parameters, making them self-documenting for LLMs.
    """
    
    def __init__(
        self,
        npl_client: NPLClient,
        cache_ttl: float = 300.0
    ):
        """
        Initialize tool generator.
        
        Args:
            npl_client: Authenticated NPL client
            cache_ttl: Cache TTL in seconds (default: 5 minutes)
        """
        self.npl_client = npl_client
        self.cache = Cache(default_ttl=cache_ttl)
        self._tools_cache: Optional[List[FunctionTool]] = None
        self._cache_time: float = 0.0
    
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
                
            elif is_action_execution_path(path, package):
                protocol_name, action_name = parse_openapi_path(path, package)
                func = self._create_action_execution_function(
                    package, protocol_name, action_name, method_spec
                )
                tool = FunctionTool(func, require_confirmation=False)
                tools.append(tool)
        
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
                    params.append({
                        "name": full_name,
                        "type": "str",  # References are IDs
                        "required": prop_name in required and not is_nullable,
                        "nullable": is_nullable,
                        "description": f"Reference ID"
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
        for p in all_params:
            req = "(required)" if p['required'] else "(optional)"
            desc = p.get('description', '')
            if p.get('enum'):
                desc = f"One of: {', '.join(p['enum'])}"
            elif p.get('format') == 'zoned-date-time':
                desc = f"DateTime string (e.g. '2025-01-15T00:00:00Z')"
            param_docs.append(f"{p['name']}: {p['type']} {req} - {desc}")
        
        func_name = f"npl_{package}_{protocol_name}_create"
        
        doc = f"""{summary}

Creates a new {protocol_name} protocol instance in the {package} package.

Args:
    {chr(10) + '    '.join(param_docs)}

Returns:
    Created protocol instance with @id, or error details if creation fails."""
        
        # Store params metadata for use in the closure
        params_meta = {p['name']: p for p in params}
        
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
                
                return self.npl_client.create_protocol(
                    package=package,
                    protocol_name=protocol_name,
                    parties=parties_dict,
                    data=data
                )
            except Exception as e:
                return {
                    "error": str(e),
                    "hint": "Check that all required fields are provided with correct types"
                }
        
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
            param_docs.append(f"    {param['name']}: {param['type']} {req}")
        
        func_name = f"npl_{package}_{protocol_name}_{action_name}"
        
        doc = f"""{summary}

Executes the {action_name} action on a {protocol_name} protocol instance.

Args:
{chr(10).join(param_docs)}

Returns:
    Action result or empty dict for void actions.
"""
        
        def impl(**kwargs) -> Dict[str, Any]:
            """Execute an action on a protocol instance."""
            try:
                instance_id = kwargs.pop("instance_id")
                party = kwargs.pop("party", None)
                return self.npl_client.execute_action(
                    package=package,
                    protocol_name=protocol_name,
                    instance_id=instance_id,
                    action_name=action_name,
                    party=party,
                    params=kwargs
                )
            except Exception as e:
                return {"error": str(e)}
        
        # Create function with typed signature so LLM can see all parameters
        return create_typed_function(func_name, doc, all_params, impl)
