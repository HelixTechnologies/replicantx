# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Supabase authentication provider for ReplicantX.

This module provides authentication via Supabase's email/password flow,
managing session tokens and providing them as Bearer tokens for API requests.
"""

import os
from typing import Dict

from supabase import create_client, Client

from .base import AuthBase, AuthenticationError
from ..models import AuthConfig


class SupabaseAuth(AuthBase):
    """Supabase authentication provider using email/password."""
    
    def __init__(self, config: AuthConfig):
        """Initialize Supabase authentication.
        
        Args:
            config: Authentication configuration with Supabase credentials
        """
        super().__init__(config)
        self._client: Client = None
        self._session = None
    
    def _get_client(self) -> Client:
        """Get or create Supabase client.
        
        Returns:
            Supabase client instance
            
        Raises:
            AuthenticationError: If client creation fails
        """
        if self._client is None:
            try:
                # Template substitution for environment variables
                project_url = self._substitute_env_vars(self.config.project_url)
                api_key = self._substitute_env_vars(self.config.api_key)
                
                self._client = create_client(project_url, api_key)
            except Exception as e:
                raise AuthenticationError(
                    f"Failed to create Supabase client: {str(e)}", 
                    "supabase"
                )
        
        return self._client
    
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
        """Authenticate with Supabase using email/password.
        
        Returns:
            Access token for API requests
            
        Raises:
            AuthenticationError: If authentication fails
        """
        try:
            client = self._get_client()
            
            # Substitute environment variables in credentials
            email = self._substitute_env_vars(self.config.email)
            password = self._substitute_env_vars(self.config.password)
            
            # Sign in with email/password
            auth_response = client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if not auth_response.session:
                raise AuthenticationError(
                    "No session returned from Supabase authentication",
                    "supabase"
                )
            
            self._session = auth_response.session
            return auth_response.session.access_token
            
        except Exception as e:
            if isinstance(e, AuthenticationError):
                raise
            raise AuthenticationError(
                f"Supabase authentication failed: {str(e)}", 
                "supabase"
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
    
    def invalidate_token(self) -> None:
        """Invalidate current session and token."""
        super().invalidate_token()
        self._session = None
        
        # Sign out from Supabase if we have a client
        if self._client:
            try:
                self._client.auth.sign_out()
            except Exception:
                # Ignore errors during sign out
                pass 