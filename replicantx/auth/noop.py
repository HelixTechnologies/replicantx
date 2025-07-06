# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
No-op authentication provider for ReplicantX.

This module provides a no-authentication provider for testing purposes
or when working with APIs that don't require authentication.
"""

from typing import Dict

from .base import AuthBase
from ..models import AuthConfig


class NoopAuth(AuthBase):
    """No-op authentication provider that provides no authentication."""
    
    def __init__(self, config: AuthConfig):
        """Initialize noop authentication.
        
        Args:
            config: Authentication configuration (not used for noop)
        """
        super().__init__(config)
    
    async def authenticate(self) -> str:
        """Return empty token for no authentication.
        
        Returns:
            Empty string (no token needed)
        """
        return ""
    
    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for HTTP requests.
        
        Returns:
            Dictionary with basic headers (no authentication)
        """
        headers = {
            "Content-Type": "application/json",
        }
        
        # Add any additional headers from config
        if self.config.headers:
            headers.update(self.config.headers)
        
        return headers 