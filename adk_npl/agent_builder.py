"""
Agent builder utilities for creating ADK agents with NPL tools.

Provides convenience functions for easy integration.
"""

import logging
import asyncio
from typing import List, Optional, Any
from google.adk.agents import LlmAgent

from .config import NPLConfig
from .client import NPLClient
from .auth import create_auth_strategy
from .tools import NPLToolGenerator
from .utils import AuthenticationError

logger = logging.getLogger(__name__)


class NPLToolRegistry:
    """
    Registry for managing NPL tools and authentication.
    
    Handles authentication, tool discovery, caching, and provides
    methods to refresh tools when needed.
    """
    
    def __init__(self, config: NPLConfig):
        """
        Initialize tool registry.
        
        Args:
            config: NPL configuration
        """
        self.config = config
        self._auth_strategy = None
        self.npl_client = NPLClient(
            base_url=config.engine_url,
            token_refresh_callback=self._refresh_token_sync
        )
        self.tool_generator = NPLToolGenerator(
            npl_client=self.npl_client,
            cache_ttl=config.cache_ttl
        )
        self._authenticated = False
    
    def _refresh_token_sync(self) -> str:
        """
        Synchronous wrapper for token refresh (for use as callback).
        
        Returns:
            New JWT access token
        """
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.run(self._refresh_token_async())
    
    async def _refresh_token_async(self) -> str:
        """
        Async token refresh.
        
        Returns:
            New JWT access token
        """
        if self._auth_strategy and hasattr(self._auth_strategy, 'refresh_token'):
            try:
                token = await self._auth_strategy.refresh_token()
                self.npl_client.set_auth_token(token)
                return token
            except Exception as e:
                logger.warning(f"Token refresh failed, re-authenticating: {e}")
                # Fall back to full authentication
                return await self._authenticate_internal()
        else:
            # Fall back to full authentication
            return await self._authenticate_internal()
    
    async def _authenticate_internal(self) -> str:
        """Internal authentication method that returns token."""
        auth_strategy = create_auth_strategy(self.config)
        if auth_strategy:
            token = await auth_strategy.authenticate()
            self._auth_strategy = auth_strategy
            return token
        raise AuthenticationError("No authentication configured")
    
    async def authenticate(self):
        """
        Authenticate with NPL Engine.
        
        Raises:
            AuthenticationError: If authentication fails
        """
        if self._authenticated and self.npl_client.auth_token:
            logger.info("Already authenticated")
            return
        
        token = await self._authenticate_internal()
        self.npl_client.set_auth_token(token)
        self._authenticated = True
        logger.info("✅ Authentication successful")
    
    async def discover_tools(
        self,
        packages: Optional[List[str]] = None,
        force_refresh: bool = False
    ) -> List[Any]:
        """
        Discover and generate tools from NPL Engine.
        
        Args:
            packages: Optional list of packages (None = auto-discover)
            force_refresh: If True, ignore cache and regenerate
            
        Returns:
            List of ADK FunctionTool instances
        """
        # Ensure authenticated
        if not self._authenticated:
            await self.authenticate()
        
        return await self.tool_generator.generate_tools(
            packages=packages,
            force_refresh=force_refresh
        )
    
    def refresh_tools(self):
        """Invalidate tool cache to force refresh on next discovery."""
        self.tool_generator._tools_cache = None
        self.tool_generator._cache_time = 0.0
        logger.info("Tool cache invalidated")


async def create_agent_with_npl(
    base_agent: LlmAgent,
    config: Optional[NPLConfig] = None,
    packages: Optional[List[str]] = None,
    additional_tools: Optional[List[Any]] = None,
    force_refresh: bool = False
) -> LlmAgent:
    """
    Create an ADK agent with NPL tools automatically added.
    
    This is the main convenience function for developers.
    
    Args:
        base_agent: Base ADK agent (without NPL tools)
        config: NPL configuration (uses from_env() if None)
        packages: Optional list of packages (None = auto-discover all)
        additional_tools: Optional additional tools to add
        force_refresh: If True, ignore cache and regenerate tools
        
    Returns:
        Agent with NPL tools added
        
    Example:
        ```python
        from adk_npl import create_agent_with_npl, NPLConfig
        from google.adk.agents import LlmAgent
        
        base_agent = LlmAgent(
            model="gemini-2.0-flash-exp",
            name="MyAgent",
            instruction="..."
        )
        
        config = NPLConfig.from_env()
        agent = await create_agent_with_npl(base_agent, config)
        # Agent now has all NPL tools!
        ```
    """
    if config is None:
        config = NPLConfig.from_env()
    
    # Validate config
    errors = config.validate()
    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")
    
    # Create registry
    registry = NPLToolRegistry(config)
    
    # Authenticate
    await registry.authenticate()
    
    # Discover NPL tools
    logger.info("Discovering NPL tools...")
    npl_tools = await registry.discover_tools(
        packages=packages,
        force_refresh=force_refresh
    )
    
    # Combine with existing tools
    existing_tools = list(base_agent.tools or [])
    all_tools = existing_tools + npl_tools
    
    if additional_tools:
        all_tools.extend(additional_tools)
    
    # Update agent with tools
    base_agent.tools = all_tools
    
    logger.info(f"✅ Agent configured with {len(npl_tools)} NPL tool(s) and {len(existing_tools)} existing tool(s)")
    
    return base_agent

