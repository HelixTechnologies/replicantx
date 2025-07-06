# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
JWT authentication provider for ReplicantX.

This module provides authentication using pre-minted JWT tokens,
typically provided via environment variables or configuration.
"""

import os
from typing import Dict

from .base import AuthBase, AuthenticationError
from ..models import AuthConfig


class JWTAuth(AuthBase):
    """JWT authentication provider using pre-minted tokens."""
    
    def __init__(self, config: AuthConfig):
        """Initialize JWT authentication.
        
        Args:
            config: Authentication configuration with JWT token
        """
        super().__init__(config)
    
    def _substitute_env_vars(self, value: str) -> str:
        """Substitute environment variables in string values.
        
        Args:
            value: String that may contain {{ env.VAR_NAME }} patterns
            
        Returns:
            String with environment variables substituted
        """
        if not value:
            return value
        
        # Simple template substitution for {{ env.VAR_NAME }}
        import re
        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                raise ValueError(f"Environment variable {var_name} not found")
            return env_value
        
        return re.sub(r'\{\{\s*env\.([A-Z_]+)\s*\}\}', replace_env_var, value)
    
    async def authenticate(self) -> str:
        """Return the JWT token.
        
        Returns:
            JWT token for API requests
            
        Raises:
            AuthenticationError: If token is missing or invalid
        """
        try:
            if not self.config.token:
                raise AuthenticationError(
                    "JWT token not provided in configuration",
                    "jwt"
                )
            
            # Substitute environment variables in token
            token = self._substitute_env_vars(self.config.token)
            
            if not token:
                raise AuthenticationError(
                    "JWT token is empty after environment variable substitution",
                    "jwt"
                )
            
            return token
            
        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            raise AuthenticationError(
                f"JWT authentication failed: {str(e)}", 
                "jwt"
            )
    
    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for HTTP requests.
        
        Returns:
            Dictionary with Authorization header
        """
        token = await self.token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        
        # Add any additional headers from config
        if self.config.headers:
            headers.update(self.config.headers)
        
        return headers 