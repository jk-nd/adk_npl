"""
Copyright 2025 Noumena Digital AG

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import re
import logging
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


class NPLProtocolParser:
    """Parse NPL protocol source files to extract workflow information."""
    
    def __init__(self, npl_file_path: Path):
        """
        Initialize parser with NPL source file.
        
        Args:
            npl_file_path: Path to .npl file
        """
        self.file_path = npl_file_path
        self.content = npl_file_path.read_text()
        self.parties: List[str] = []
        self.protocol_name: Optional[str] = None
        self.states: Dict[str, str] = {}  # name -> type (initial/state/final)
        self.permissions: List[Dict] = []
        self.imports: List[str] = []
        self.requirements: List[str] = [] # Global requirements (in init)
        
    def parse(self) -> Dict:
        """Parse the NPL file and extract protocol information."""
        self._extract_protocol_name()
        self._extract_imports()
        self._extract_parties()
        self._extract_states()
        self._extract_global_requirements()
        self._extract_permissions()
        
        return {
            "protocol_name": self.protocol_name,
            "parties": self.parties,
            "states": self.states,
            "permissions": self.permissions,
            "imports": self.imports,
            "global_requirements": self.requirements
        }

    def _extract_protocol_name(self):
        """Extract protocol name from @api protocol declaration."""
        match = re.search(r'protocol\[.*?\]\s+(\w+)', self.content)
        if match:
            self.protocol_name = match.group(1)

    def _extract_imports(self):
        """Extract 'use' statements for schema discovery."""
        matches = re.findall(r'use\s+([\w\.]+);', self.content)
        self.imports = matches

    def _extract_parties(self):
        """Extract parties from protocol declaration."""
        match = re.search(r'protocol\[([^\]]+)\]', self.content)
        if match:
            parties_str = match.group(1)
            self.parties = [p.strip() for p in parties_str.split(',')]

    def _extract_states(self):
        """Extract state declarations."""
        # Match: initial state X; or state X; or final state X;
        pattern = r'(initial\s+)?(final\s+)?state\s+(\w+);'
        for match in re.finditer(pattern, self.content):
            is_initial = bool(match.group(1))
            is_final = bool(match.group(2))
            state_name = match.group(3)
            
            if is_initial:
                self.states[state_name] = "initial"
            elif is_final:
                self.states[state_name] = "final"
            else:
                self.states[state_name] = "state"

    def _extract_global_requirements(self):
        """Extract 'require' statements from the protocol body (init logic)."""
        # Find requires that are NOT inside a permission block
        first_perm = self.content.find('permission')
        prefix = self.content[:first_perm] if first_perm > 0 else self.content
        
        matches = re.findall(r'require\s*\([^,]+,\s*"([^"]+)"\s*\);', prefix)
        self.requirements = matches

    def _extract_permissions(self):
        """Extract permission declarations with state constraints and requirements."""
        # Match: permission[party] action(params) | State1, State2 { ... }
        # Simplified regex to match name and state constraints reliably
        pattern = r'permission\[([^\]]+)\]\s+(\w+)(\([^)]*\))?\s*(?:returns\s+[^{|]+)?\s*\|\s*([^\s{]+)\s*\{'
        
        for match in re.finditer(pattern, self.content):
            parties_str = match.group(1)
            action_name = match.group(2)
            params = match.group(3) or ""
            state_constraint = match.group(4)
            
            # Extract state transitions and requires from the body
            body_start = match.end()
            brace_count = 1
            body_end = body_start
            while brace_count > 0 and body_end < len(self.content):
                if self.content[body_end] == '{':
                    brace_count += 1
                elif self.content[body_end] == '}':
                    brace_count -= 1
                body_end += 1
            
            body = self.content[body_start:body_end-1]
            
            # Extract "become" statements
            become_matches = re.findall(r'become\s+(\w+);', body)
            target_states = become_matches if become_matches else []
            
            # Extract "require" statements (business rules)
            require_matches = re.findall(r'require\s*\([^,]+,\s*"([^"]+)"\s*\);', body)
            
            # Extract notification calls
            notify_matches = re.findall(r'notify\s+(\w+)', body)
            notifications = notify_matches if notify_matches else []
            
            parties = [p.strip() for p in parties_str.split('|')]
            source_states = [s.strip() for s in state_constraint.split(',')]
            
            self.permissions.append({
                "parties": parties,
                "action": action_name,
                "params": params,
                "source_states": source_states,
                "target_states": target_states,
                "notifications": notifications,
                "requirements": require_matches
            })


def generate_plantuml_sequence(protocol_info: Dict) -> str:
    """
    Generate PlantUML sequence diagram from parsed protocol information.
    
    Args:
        protocol_info: Parsed protocol information from NPLProtocolParser
        
    Returns:
        PlantUML sequence diagram as string
    """
    protocol_name = protocol_info["protocol_name"]
    parties = protocol_info["parties"]
    permissions = protocol_info["permissions"]
    
    lines = [
        "@startuml",
        f"title {protocol_name} Workflow Sequence",
        "",
        "autonumber",
        ""
    ]
    
    # Add participants
    for party in parties:
        lines.append(f"participant \"{party.title()}\" as {party}")
    
    lines.append("participant \"NPL Engine\" as engine")
    lines.append("")
    
    # Generate sequence from permissions (ordered by typical workflow)
    # Group by source state to show state-based flow
    state_flow = {}
    for perm in permissions:
        for source_state in perm["source_states"]:
            if source_state not in state_flow:
                state_flow[source_state] = []
            state_flow[source_state].append(perm)
    
    # Start from initial state
    initial_states = [s for s, t in protocol_info["states"].items() if t == "initial"]
    if initial_states:
        current_state = initial_states[0]
        visited_states = set()
        
        def add_transitions(state: str, indent: int = 0):
            if state in visited_states:
                return
            visited_states.add(state)
            
            if state in state_flow:
                for perm in state_flow[state]:
                    # Find first party (usually the one who initiates)
                    party = perm["parties"][0] if perm["parties"] else "unknown"
                    action = perm["action"]
                    params = perm["params"]
                    
                    # Build action call
                    action_call = f"{action}{params}"
                    
                    lines.append("  " * indent + f"{party} -> engine: {action_call}")
                    lines.append("  " * indent + f"note right: State: {state}")
                    
                    # Add notifications
                    for notif in perm["notifications"]:
                        lines.append("  " * indent + f"engine -> engine: notify {notif}")
                    
                    # Add state transitions
                    for target_state in perm["target_states"]:
                        lines.append("  " * indent + f"engine --> {party}: State: {target_state}")
                        add_transitions(target_state, indent + 1)
    
    if initial_states:
        add_transitions(initial_states[0])
    
    lines.append("")
    lines.append("@enduml")
    
    return "\n".join(lines)


def generate_workflow_summary(protocol_info: Dict) -> str:
    """
    Generate a text summary of the workflow for tool descriptions.
    
    Args:
        protocol_info: Parsed protocol information
        
    Returns:
        Markdown-formatted workflow summary
    """
    protocol_name = protocol_info["protocol_name"]
    parties = protocol_info["parties"]
    permissions = protocol_info["permissions"]
    global_reqs = protocol_info.get("global_requirements", [])
    imports = protocol_info.get("imports", [])
    
    lines = [
        f"## {protocol_name} Workflow",
        "",
        "### Parties:",
        ", ".join(parties),
        "",
    ]
    
    # Add Schema Context if found
    schema_context = []
    for imp in imports:
        if "schemaorg" in imp:
            schema_type = imp.split('.')[-1]
            schema_context.append(f"- `{schema_type}`: Follows schema.org standards.")
            
    if schema_context:
        lines.append("### Data Types & Standards:")
        lines.extend(schema_context)
        lines.append("")

    # Add Global Requirements
    if global_reqs:
        lines.append("### Business Rules (Global):")
        for req in global_reqs:
            lines.append(f"- Rule: {req}")
        lines.append("")
    
    lines.append("### State Flow:")
    
    # Build state transition map
    transitions = {}
    for perm in permissions:
        for source_state in perm["source_states"]:
            if source_state not in transitions:
                transitions[source_state] = []
            transitions[source_state].extend(perm["target_states"])
    
    # Show state flow
    initial_states = [s for s, t in protocol_info["states"].items() if t == "initial"]
    if initial_states:
        current = initial_states[0]
        path = []
        visited = set()
        
        def build_path(state: str):
            if state in visited:
                return
            visited.add(state)
            path.append(state)
            
            if state in transitions:
                for next_state in transitions[state]:
                    if next_state not in visited:
                        build_path(next_state)
        
        build_path(current)
        lines.append(" → ".join(path))
    
    lines.append("")
    lines.append("### Actions by Party:")
    
    # Group permissions by party
    by_party = {}
    for perm in permissions:
        for party in perm["parties"]:
            if party not in by_party:
                by_party[party] = []
            by_party[party].append(perm)
    
    for party, perms in by_party.items():
        lines.append(f"\n**{party.title()}:**")
        for perm in perms:
            states_str = ", ".join(perm["source_states"])
            targets_str = ", ".join(perm["target_states"]) if perm["target_states"] else "no transition"
            lines.append(f"- `{perm['action']}` (from: {states_str} → {targets_str})")
            # Add action-specific requirements
            if perm.get("requirements"):
                for req in perm["requirements"]:
                    lines.append(f"  * Requirement: {req}")
    
    return "\n".join(lines)


def generate_diagram_for_protocol(npl_file_path: Path) -> Optional[str]:
    """
    Generate PlantUML diagram for a single NPL protocol file.
    
    Args:
        npl_file_path: Path to .npl file
        
    Returns:
        PlantUML diagram string or None if parsing fails
    """
    try:
        parser = NPLProtocolParser(npl_file_path)
        protocol_info = parser.parse()
        
        if not protocol_info["protocol_name"]:
            logger.warning(f"Could not extract protocol name from {npl_file_path}")
            return None
        
        return generate_plantuml_sequence(protocol_info)
    except Exception as e:
        logger.error(f"Failed to generate diagram for {npl_file_path}: {e}")
        return None


def generate_workflow_summary_for_protocol(npl_file_path: Path) -> Optional[str]:
    """
    Generate workflow summary for a single NPL protocol file.
    
    Args:
        npl_file_path: Path to .npl file
        
    Returns:
        Markdown workflow summary or None if parsing fails
    """
    try:
        parser = NPLProtocolParser(npl_file_path)
        protocol_info = parser.parse()
        
        if not protocol_info["protocol_name"]:
            logger.warning(f"Could not extract protocol name from {npl_file_path}")
            return None
        
        return generate_workflow_summary(protocol_info)
    except Exception as e:
        logger.error(f"Failed to generate summary for {npl_file_path}: {e}")
        return None


# =============================================================================
# AGENT WORKFLOW CONTEXT GENERATOR
# =============================================================================

def generate_agent_workflow_guide(npl_file_path: Path) -> Optional[Dict]:
    """
    Generate a compact workflow guide optimized for agent instructions.
    
    This extracts the essential information an agent needs to understand
    and execute protocol workflows correctly:
    - State machine (what states exist, which are initial/final)
    - Transitions (what actions move between states)
    - Party roles (who can do what)
    - Business rules (requirements that must be satisfied)
    
    Args:
        npl_file_path: Path to .npl file
        
    Returns:
        Dict with structured workflow information for agent context
    """
    try:
        parser = NPLProtocolParser(npl_file_path)
        info = parser.parse()
        
        if not info["protocol_name"]:
            return None
        
        # Build state machine representation
        states = info["states"]
        initial = [s for s, t in states.items() if t == "initial"]
        finals = [s for s, t in states.items() if t == "final"]
        intermediates = [s for s, t in states.items() if t == "state"]
        
        # Build action map: who can do what from which state
        actions_by_party = {}
        transitions = []
        
        for perm in info["permissions"]:
            action = perm["action"]
            parties = perm["parties"]
            source_states = perm["source_states"]
            target_states = perm["target_states"]
            requirements = perm.get("requirements", [])
            
            # Track transitions
            for source in source_states:
                for target in target_states:
                    transitions.append({
                        "action": action,
                        "from": source,
                        "to": target,
                        "by": parties,
                        "rules": requirements
                    })
            
            # Group by party
            for party in parties:
                if party not in actions_by_party:
                    actions_by_party[party] = []
                actions_by_party[party].append({
                    "action": action,
                    "when": source_states,
                    "then": target_states if target_states else ["same state"],
                    "rules": requirements
                })
        
        return {
            "protocol": info["protocol_name"],
            "parties": info["parties"],
            "states": {
                "initial": initial,
                "intermediate": intermediates,
                "final": finals,
                "all": list(states.keys())
            },
            "actions_by_party": actions_by_party,
            "transitions": transitions,
            "global_rules": info.get("global_requirements", [])
        }
    except Exception as e:
        logger.error(f"Failed to generate workflow guide for {npl_file_path}: {e}")
        return None


def format_workflow_guide_for_agent(guide: Dict) -> str:
    """
    Format a workflow guide as concise text for agent instructions.
    
    Args:
        guide: Workflow guide dict from generate_agent_workflow_guide
        
    Returns:
        Formatted string for agent context
    """
    if not guide:
        return ""
    
    lines = [
        f"### {guide['protocol']} Protocol",
        f"**Parties:** {', '.join(guide['parties'])}",
        ""
    ]
    
    # State machine
    states = guide["states"]
    lines.append("**State Machine:**")
    state_flow = " → ".join(
        states["initial"] + 
        states["intermediate"] + 
        states["final"]
    )
    lines.append(f"`{state_flow}`")
    lines.append("")
    
    # Actions by party (most important for the agent!)
    lines.append("**Your Available Actions:**")
    for party, actions in guide["actions_by_party"].items():
        lines.append(f"\n*As {party}:*")
        for act in actions:
            when_str = ", ".join(act["when"])
            then_str = ", ".join(act["then"])
            lines.append(f"- `{act['action']}()` — when state is [{when_str}] → [{then_str}]")
            if act["rules"]:
                for rule in act["rules"]:
                    lines.append(f"  ⚠️ Rule: {rule}")
    
    # Global rules
    if guide["global_rules"]:
        lines.append("\n**Business Rules:**")
        for rule in guide["global_rules"]:
            lines.append(f"- {rule}")
    
    return "\n".join(lines)


def generate_all_workflow_guides(npl_source_dir: Path, packages: List[str] = None) -> str:
    """
    Generate workflow guides for all protocols in specified packages.
    
    This is the main function to call from agent_factory.py to get
    all workflow context for agent instructions.
    
    Args:
        npl_source_dir: Base path to NPL sources (e.g., npl/src/main/npl-1.0)
        packages: List of package names to process (default: all)
        
    Returns:
        Combined workflow guide text for all protocols
    """
    guides = []
    
    # Find all .npl files in packages
    if not npl_source_dir.exists():
        logger.warning(f"NPL source dir not found: {npl_source_dir}")
        return ""
    
    # Search for NPL files
    search_paths = []
    if packages:
        for pkg in packages:
            pkg_dir = npl_source_dir / pkg
            if pkg_dir.exists():
                search_paths.extend(pkg_dir.glob("*.npl"))
    else:
        search_paths = list(npl_source_dir.rglob("*.npl"))
    
    for npl_file in search_paths:
        guide = generate_agent_workflow_guide(npl_file)
        if guide:
            formatted = format_workflow_guide_for_agent(guide)
            guides.append(formatted)
            logger.debug(f"Generated workflow guide for {guide['protocol']}")
    
    if not guides:
        logger.warning("No workflow guides generated")
        return ""
    
    result = "\n\n---\n\n".join(guides)
    logger.info(f"Generated {len(guides)} workflow guides ({len(result)} chars)")
    return result


def parse_puml_for_structure(puml_file_path: Path) -> Optional[Dict]:
    """
    Parse a .puml file (from npl puml) to extract protocol structure.
    
    Complements the .npl parsing by providing:
    - Field definitions with types
    - Method signatures with party roles
    - Relationships to other protocols
    
    Args:
        puml_file_path: Path to .puml file
        
    Returns:
        Dict with protocol structure information
    """
    try:
        content = puml_file_path.read_text()
        
        # Extract class name
        class_match = re.search(r'class (\w+)', content)
        protocol_name = class_match.group(1) if class_match else None
        
        # Extract fields: {field} +fieldName: Type
        fields = []
        for match in re.finditer(r'\{field\}\s+\+(\w+):\s+([^\n]+)', content):
            fields.append({
                "name": match.group(1),
                "type": match.group(2).strip()
            })
        
        # Extract methods: {method} +[party] methodName(params)
        methods = []
        for match in re.finditer(r'\{method\}\s+\+\[([^\]]+)\]\s+(\w+)\(([^)]*)\)', content):
            methods.append({
                "parties": [p.strip() for p in match.group(1).split('|')],
                "name": match.group(2),
                "params": match.group(3).strip()
            })
        
        # Extract relationships: --> "1" other.Protocol : fieldName
        relationships = []
        for match in re.finditer(r'--> "[\d*]" ([^\s:]+)', content):
            relationships.append(match.group(1))
        
        return {
            "protocol": protocol_name,
            "fields": fields,
            "methods": methods,
            "relationships": relationships
        }
    except Exception as e:
        logger.error(f"Failed to parse puml {puml_file_path}: {e}")
        return None


def format_puml_structure_for_agent(puml_info: Dict) -> str:
    """
    Format puml structure as concise text for agent instructions.
    
    Args:
        puml_info: Structure dict from parse_puml_for_structure
        
    Returns:
        Formatted string for agent context
    """
    if not puml_info:
        return ""
    
    lines = [
        f"### {puml_info['protocol']} Structure",
        ""
    ]
    
    # Fields (key data the agent needs to provide)
    if puml_info["fields"]:
        lines.append("**Fields:**")
        for f in puml_info["fields"]:
            lines.append(f"- `{f['name']}`: {f['type']}")
        lines.append("")
    
    # Methods with party roles
    if puml_info["methods"]:
        lines.append("**Methods:**")
        for m in puml_info["methods"]:
            parties = " | ".join(m["parties"])
            params = m["params"] if m["params"] else ""
            lines.append(f"- `{m['name']}({params})` — [{parties}]")
        lines.append("")
    
    # Relationships (what other protocols are referenced)
    if puml_info["relationships"]:
        lines.append("**References:**")
        for r in puml_info["relationships"]:
            lines.append(f"- {r}")
    
    return "\n".join(lines)

