"""
Smart docstring trimmer for NPL tools.

Reduces token usage by 80%+ while preserving semantic information
critical for LLM understanding.
"""

import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class DocstringTrimmer:
    """
    Condenses verbose tool docstrings while preserving semantic value.
    
    Keeps:
    - Protocol/action name and purpose
    - Party roles and their allowed actions
    - State transitions
    - Required parameters with types
    - Critical warnings (multi-party, references)
    
    Removes:
    - Emoji decorations
    - Redundant headers
    - Schema.org URLs (keep concept, drop URL)
    - Verbose explanations
    - Repetitive warnings
    """
    
    @staticmethod
    def _extract_party_actions(docstring: str) -> str:
        """Extract party roles and actions in condensed format."""
        # Look for "**party** can perform:" sections
        party_pattern = r'\*\*(\w+)\*\* can perform:(.*?)(?=\*\*\w+\*\* can perform:|\n\n|###|\Z)'
        matches = re.findall(party_pattern, docstring, re.DOTALL)
        
        if not matches:
            return ""
        
        result = []
        for party, actions in matches:
            # Extract action names (e.g., "- publish: Description")
            action_names = re.findall(r'- (\w+):', actions)
            if action_names:
                result.append(f"{party}: {'/'.join(action_names)}")
        
        return "Parties: " + ", ".join(result) if result else ""
    
    @staticmethod
    def _extract_states(docstring: str) -> str:
        """Extract state transitions in condensed format."""
        # Look for "Valid from States" and "Transition to States"
        from_match = re.search(r'Valid from States?:\s*([^\n]+)', docstring)
        to_match = re.search(r'Transition to States?:\s*([^\n]+)', docstring)
        
        if not from_match and not to_match:
            return ""
        
        from_states = from_match.group(1).strip() if from_match else "any"
        to_states = to_match.group(1).strip() if to_match else "unchanged"
        
        # Clean up
        from_states = from_states.replace("None (creation action)", "new")
        
        return f"States: {from_states} → {to_states}"
    
    @staticmethod
    def _extract_parameters(docstring: str) -> str:
        """Extract parameters in condensed format, preserving enum values."""
        # Look for Args: section with parameter descriptions
        args_match = re.search(r'Args?:(.*?)(?=Returns?:|\n\n\w|\Z)', docstring, re.DOTALL | re.IGNORECASE)
        if args_match:
            args_section = args_match.group(1)
            # Extract each parameter line (indented lines after Args:)
            param_lines = []
            for line in args_section.strip().split('\n'):
                line = line.strip()
                if ':' in line and line:
                    # Keep enum values (One of: ...) but shorten other descriptions
                    if 'One of:' in line:
                        param_lines.append(line)  # Keep full enum description
                    elif '(required)' in line or '(optional)' in line:
                        # Keep name, type, and required/optional
                        param_lines.append(line.split(' - ')[0])  # Just the "name: type (required)" part
                    else:
                        param_lines.append(line)
            if param_lines:
                return "Params:\n  " + "\n  ".join(param_lines)
        
        # Fallback: look for "Parameters:" section
        params_match = re.search(r'Parameters?:(.*?)(?=\n\n|\Z)', docstring, re.DOTALL)
        if params_match:
            param_lines = re.findall(r'^\s+(\w+):', params_match.group(1), re.MULTILINE)
            if param_lines:
                return "Params: " + ", ".join(param_lines)
        
        return ""
    
    @staticmethod
    def _extract_warnings(docstring: str) -> str:
        """Extract critical warnings, including protocol dependency sequences and role information."""
        warnings = []
        
        # WHO CREATES THIS PROTOCOL? (CRITICAL for role awareness)
        if "WHO CREATES THIS PROTOCOL?" in docstring:
            # Extract the creator party and initial state
            creator_match = re.search(r'\*\*Typically created by: (\w+)\*\*\s*(?:\(starts in \'(\w+)\' state\))?', docstring)
            if creator_match:
                creator = creator_match.group(1)
                initial_state = creator_match.group(2)
                if initial_state:
                    warnings.append(f"CREATOR: {creator} (from {initial_state} state)")
                else:
                    warnings.append(f"CREATOR: {creator}")
            
            # Extract the CRITICAL PRINCIPLE about workflow start
            if "Am I at the START of this protocol's workflow?" in docstring:
                warnings.append("Only create if at workflow START")
            
            # Extract party actions to help agent decide
            actions_section = re.search(r'\*\*What can each party DO after creation\?\*\*\s*(.*?)(?=\n\n|\*\*)', docstring, re.DOTALL)
            if actions_section:
                # Extract simplified party -> actions mapping
                party_lines = re.findall(r'- \*\*(\w+)\*\* can: ([^\n]+)', actions_section.group(1))
                if party_lines:
                    for party, actions in party_lines[:2]:  # Keep first 2 parties
                        # Simplify action list (first 3 actions)
                        action_list = [a.strip() for a in actions.split(',')[:3]]
                        warnings.append(f"{party} → {', '.join(action_list)}")
        
        # Multi-party protocol warning (fallback if WHO CREATES not found)
        elif "MULTI-PARTY" in docstring:
            warnings.append("multi-party (check roles)")
        
        # Protocol dependency sequence (CRITICAL for workflow)
        if "PROTOCOL DEPENDENCY SEQUENCE" in docstring:
            # Extract the "REQUIRED SEQUENCE:" line
            seq_match = re.search(r'\*\*REQUIRED SEQUENCE:\*\*\s*\n([^\n]+)', docstring)
            if seq_match:
                sequence = seq_match.group(1).strip()
                warnings.append(f"SEQUENCE: {sequence}")
            else:
                # Fallback: look for reference fields
                ref_match = re.search(r'\*\*Reference Fields:\*\*(.*?)(?=\*\*|$)', docstring, re.DOTALL)
                if ref_match:
                    # Extract field names that need UUIDs
                    ref_fields = re.findall(r'- \*\*(\w+)\*\*:', ref_match.group(1))
                    if ref_fields:
                        warnings.append(f"NEEDS: {' → '.join(ref_fields)} (UUIDs)")
        
        # Generic reference field warning (if no sequence detected)
        elif "REFERENCE field" in docstring or ("UUID" in docstring and "protocol instance" in docstring):
            ref_fields = re.findall(r'\*\*(\w+)\*\*.*?UUID.*?protocol instance', docstring, re.DOTALL)
            if ref_fields:
                warnings.append(f"refs: {','.join(ref_fields[:2])} need UUIDs")
        
        return "⚠️ " + "; ".join(warnings) if warnings else ""
    
    @classmethod
    def trim(cls, docstring: str) -> str:
        """
        Trim a docstring to essential information only.
        
        Args:
            docstring: Original verbose docstring
            
        Returns:
            Condensed docstring (~80% token reduction)
        """
        if not docstring or len(docstring) < 100:
            return docstring  # Already short
        
        # Extract first line (usually the main description)
        first_line = docstring.split('\n')[0].strip()
        
        # Extract structured information
        party_actions = cls._extract_party_actions(docstring)
        states = cls._extract_states(docstring)
        parameters = cls._extract_parameters(docstring)
        warnings = cls._extract_warnings(docstring)
        
        # Build condensed docstring
        parts = [first_line]
        if party_actions:
            parts.append(party_actions)
        if states:
            parts.append(states)
        if parameters:
            parts.append(parameters)
        if warnings:
            parts.append(warnings)
        
        condensed = "\n".join(parts)
        
        # Log reduction
        original_tokens = len(docstring) // 4
        condensed_tokens = len(condensed) // 4
        reduction = 100 - (condensed_tokens * 100 // original_tokens) if original_tokens > 0 else 0
        
        logger.debug(
            f"Docstring trimmed: {original_tokens} → {condensed_tokens} tokens "
            f"({reduction}% reduction)"
        )
        
        return condensed


def trim_tool_docstrings(tools: list) -> list:
    """
    Trim docstrings for a list of FunctionTool instances.
    
    Args:
        tools: List of FunctionTool instances
        
    Returns:
        Same list with trimmed docstrings (modified in place)
    """
    trimmer = DocstringTrimmer()
    trimmed_count = 0
    
    for tool in tools:
        if hasattr(tool, 'func') and hasattr(tool.func, '__doc__') and tool.func.__doc__:
            original_doc = tool.func.__doc__
            trimmed_doc = trimmer.trim(original_doc)
            tool.func.__doc__ = trimmed_doc
            trimmed_count += 1
        elif hasattr(tool, 'description') and tool.description:
            original_desc = tool.description
            trimmed_desc = trimmer.trim(original_desc)
            tool.description = trimmed_desc
            trimmed_count += 1
    
    logger.info(f"📉 Trimmed docstrings for {trimmed_count}/{len(tools)} tools")
    return tools

