"""
Configuration management for ADK-NPL integration.

Supports loading configuration from environment variables, dictionaries, or YAML files.
"""

import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()


class NPLConfig:
    """
    Configuration for NPL Engine integration.
    
    Supports multiple ways to load configuration:
    - Environment variables
    - Dictionary
    - YAML file
    """
    
    def __init__(
        self,
        engine_url: str = "http://localhost:12000",
        keycloak_url: Optional[str] = None,
        keycloak_realm: Optional[str] = None,
        keycloak_client_id: str = "npl-client",
        packages: Optional[List[str]] = None,
        auth_method: str = "keycloak",  # "keycloak", "token", "none"
        credentials: Optional[Dict[str, str]] = None,
        cache_ttl: float = 300.0,  # 5 minutes
        swagger_ui_path: str = "/swagger-ui/"
    ):
        """
        Initialize NPL configuration.
        
        Args:
            engine_url: NPL Engine base URL
            keycloak_url: Keycloak base URL (for authentication)
            keycloak_realm: Keycloak realm name
            keycloak_client_id: Keycloak client ID
            packages: Optional list of packages (if None, will auto-discover)
            auth_method: Authentication method ("keycloak", "token", "none")
            credentials: Authentication credentials dict
                - For keycloak: {"username": "...", "password": "..."}
                - For token: {"token": "..."}
            cache_ttl: Cache TTL in seconds (default: 5 minutes)
            swagger_ui_path: Path to Swagger UI (default: "/swagger-ui/")
        """
        self.engine_url = engine_url.rstrip('/')
        self.keycloak_url = keycloak_url
        self.keycloak_realm = keycloak_realm
        self.keycloak_client_id = keycloak_client_id
        self.packages = packages
        self.auth_method = auth_method
        self.credentials = credentials or {}
        self.cache_ttl = cache_ttl
        self.swagger_ui_path = swagger_ui_path
    
    @classmethod
    def from_env(cls) -> 'NPLConfig':
        """
        Create configuration from environment variables.
        
        Environment variables:
            NPL_ENGINE_URL: NPL Engine base URL
            NPL_KEYCLOAK_URL: Keycloak base URL
            NPL_KEYCLOAK_REALM: Keycloak realm
            NPL_KEYCLOAK_CLIENT_ID: Keycloak client ID
            NPL_PACKAGES: Comma-separated list of packages
            NPL_USERNAME: Username for Keycloak auth
            NPL_PASSWORD: Password for Keycloak auth
            NPL_TOKEN: Direct auth token
            NPL_CACHE_TTL: Cache TTL in seconds
        """
        engine_url = os.getenv("NPL_ENGINE_URL", "http://localhost:12000")
        keycloak_url = os.getenv("NPL_KEYCLOAK_URL")
        keycloak_realm = os.getenv("NPL_KEYCLOAK_REALM")
        keycloak_client_id = os.getenv("NPL_KEYCLOAK_CLIENT_ID", "npl-client")
        
        # Parse packages
        packages_str = os.getenv("NPL_PACKAGES")
        packages = None
        if packages_str:
            packages = [p.strip() for p in packages_str.split(",")]
        
        # Determine auth method
        auth_method = "none"
        credentials = {}
        
        if os.getenv("NPL_TOKEN"):
            auth_method = "token"
            credentials["token"] = os.getenv("NPL_TOKEN")
        elif os.getenv("NPL_USERNAME") and os.getenv("NPL_PASSWORD"):
            auth_method = "keycloak"
            credentials["username"] = os.getenv("NPL_USERNAME")
            credentials["password"] = os.getenv("NPL_PASSWORD")
        
        cache_ttl = float(os.getenv("NPL_CACHE_TTL", "300"))
        
        return cls(
            engine_url=engine_url,
            keycloak_url=keycloak_url,
            keycloak_realm=keycloak_realm,
            keycloak_client_id=keycloak_client_id,
            packages=packages,
            auth_method=auth_method,
            credentials=credentials,
            cache_ttl=cache_ttl
        )
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'NPLConfig':
        """
        Create configuration from dictionary.
        
        Args:
            config_dict: Configuration dictionary
        """
        return cls(**config_dict)
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> 'NPLConfig':
        """
        Create configuration from YAML file.
        
        Args:
            yaml_path: Path to YAML configuration file
        """
        try:
            import yaml
        except ImportError:
            raise ImportError(
                "PyYAML is required for YAML config. Install with: pip install pyyaml"
            )
        
        with open(yaml_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        
        # Flatten nested structure if needed
        if 'npl' in config_dict:
            config_dict = config_dict['npl']
        
        return cls.from_dict(config_dict)
    
    def get_keycloak_url(self) -> Optional[str]:
        """Get Keycloak URL, with fallback to engine URL if not set."""
        if self.keycloak_url:
            return self.keycloak_url.rstrip('/')
        # Try to infer from engine URL (common pattern)
        if 'localhost' in self.engine_url or '127.0.0.1' in self.engine_url:
            # Replace port 12000 with 11000 (common Keycloak port)
            return self.engine_url.replace(':12000', ':11000')
        return None
    
    def get_keycloak_realm(self) -> str:
        """Get Keycloak realm, with default."""
        return self.keycloak_realm or "poc"
    
    def validate(self) -> List[str]:
        """
        Validate configuration and return list of errors.
        
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        if not self.engine_url:
            errors.append("engine_url is required")
        
        if self.auth_method == "keycloak":
            if not self.get_keycloak_url():
                errors.append("keycloak_url is required for keycloak auth")
            if not self.get_keycloak_realm():
                errors.append("keycloak_realm is required for keycloak auth")
            if not self.credentials.get("username"):
                errors.append("username is required for keycloak auth")
            if not self.credentials.get("password"):
                errors.append("password is required for keycloak auth")
        
        if self.auth_method == "token":
            if not self.credentials.get("token"):
                errors.append("token is required for token auth")
        
        return errors

