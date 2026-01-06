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
import os
import json
import requests
import logging
from typing import List, Optional
from pathlib import Path

from .client import NPLClient
from .utils import PackageDiscoveryError
from .config import NPLConfig

logger = logging.getLogger(__name__)


class NPLPackageDiscovery:
    """
    Discovers available NPL packages from NPL Engine.
    
    Strategy (in order of priority):
    1. Parse Swagger UI HTML to extract package URLs
    2. Read from npl-packages.json config file
    3. Read from NPL_PACKAGES environment variable
    """
    
    def __init__(self, engine_url_or_config):
        """
        Initialize package discovery.
        
        Args:
            engine_url_or_config: NPL Engine base URL (str) or NPLConfig object
        """
        if isinstance(engine_url_or_config, NPLConfig):
            self.engine_url = engine_url_or_config.engine_url.rstrip('/')
        else:
            self.engine_url = str(engine_url_or_config).rstrip('/')
    
    async def discover_packages(self) -> List[str]:
        """
        Discover all available NPL packages.
        
        Returns:
            List of package names (may include paths like "objects/iou")
            
        Raises:
            PackageDiscoveryError: If discovery fails
        """
        # Try Swagger UI first (primary method)
        try:
            packages = self._discover_from_swagger_ui()
            if packages:
                logger.info(f"✅ Discovered {len(packages)} package(s) from Swagger UI: {', '.join(packages)}")
                return packages
        except Exception as e:
            logger.warning(f"⚠️  Swagger UI discovery failed: {e}")
        
        # Fallback: Config file
        try:
            packages = self._discover_from_config_file()
            if packages:
                logger.info(f"✅ Using packages from config file: {', '.join(packages)}")
                return packages
        except Exception as e:
            logger.warning(f"⚠️  Config file discovery failed: {e}")
        
        # Fallback: Environment variable
        try:
            packages = self._discover_from_env()
            if packages:
                logger.info(f"✅ Using packages from environment: {', '.join(packages)}")
                return packages
        except Exception as e:
            logger.warning(f"⚠️  Environment variable discovery failed: {e}")
        
        # All methods failed
        raise PackageDiscoveryError(
            f"Could not discover NPL packages. Please check:\n"
            f"  1. NPL Engine is running at {self.engine_url}\n"
            f"  2. Swagger UI is accessible at {self.engine_url}/swagger-ui/\n"
            f"  3. Or configure packages in npl-packages.json or NPL_PACKAGES env var"
        )
    
    def _discover_from_swagger_ui(self) -> List[str]:
        """
        Discover packages by parsing Swagger UI HTML.
        
        This is the primary method - fully dynamic, no configuration needed!
        
        Returns:
            List of package names
            
        Raises:
            PackageDiscoveryError: If Swagger UI is not accessible
        """
        swagger_url = f"{self.engine_url}/swagger-ui/"
        logger.info(f"📡 Discovering packages from Swagger UI: {swagger_url}")
        
        try:
            response = requests.get(swagger_url, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise PackageDiscoveryError(f"Failed to fetch Swagger UI: {e}") from e
        
        html = response.text
        
        # Extract all /npl/{package}/-/openapi.json URLs
        # Pattern matches:
        #   - /npl/protocolpackage/-/openapi.json → "protocolpackage"
        #   - /npl/objects/iou/-/openapi.json → "objects/iou"
        regex = re.compile(r'/npl/([^"\'/]+(?:/[^"\'/]+)*)/-/openapi\.json')
        matches = regex.findall(html)
        
        # Get unique package names
        packages = list(set(matches))
        
        if not packages:
            raise PackageDiscoveryError("No packages found in Swagger UI")
        
        return packages
    
    def _discover_from_config_file(self) -> List[str]:
        """
        Fallback: Read from npl-packages.json config file.
        
        Looks for file in current directory or parent directories.
        
        Returns:
            List of package names
            
        Raises:
            PackageDiscoveryError: If file not found or invalid
        """
        # Try current directory and parent directories
        search_paths = [
            Path.cwd() / "npl-packages.json",
            Path.cwd() / "public" / "npl-packages.json",
            Path(__file__).parent.parent / "npl-packages.json",
        ]
        
        for config_path in search_paths:
            if config_path.exists():
                logger.info(f"📋 Reading packages from: {config_path}")
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                    
                    packages = config.get("packages", [])
                    if packages:
                        return packages
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Invalid config file format: {e}")
                    continue
        
        raise PackageDiscoveryError("npl-packages.json not found")
    
    def _discover_from_env(self) -> List[str]:
        """
        Fallback: Read from NPL_PACKAGES environment variable.
        
        Returns:
            List of package names
            
        Raises:
            PackageDiscoveryError: If env var not set
        """
        packages_str = os.getenv("NPL_PACKAGES")
        if not packages_str:
            raise PackageDiscoveryError("NPL_PACKAGES environment variable not set")
        
        packages = [p.strip() for p in packages_str.split(",") if p.strip()]
        if not packages:
            raise PackageDiscoveryError("NPL_PACKAGES is empty")
        
        return packages

