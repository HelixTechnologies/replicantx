# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Base authentication class for ReplicantX.

This module defines the abstract base class that all authentication providers
must inherit from to provide a consistent interface.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional

from ..models import AuthConfig


class AuthBase(ABC):
    """Abstract base class for authentication providers."""
    
    def __init__(self, config: AuthConfig):
        """Initialize the authentication provider.
        
        Args:
            config: Authentication configuration
        """
        self.config = config
        self._token: Optional[str] = None
        self._headers: Dict[str, str] = {}
    
    @abstractmethod
    async def authenticate(self) -> str:
        """Authenticate and return a token.
        
        Returns:
            Authentication token
            
        Raises:
            AuthenticationError: If authentication fails
        """
        pass
    
    @abstractmethod
    async def get_headers(self) -> Dict[str, str]:
        """Get authentication headers for HTTP requests.
        
        Returns:
            Dictionary of headers to include in requests
        """
        pass
    
    async def token(self) -> str:
        """Get the current authentication token.
        
        This method caches the token and only re-authenticates if necessary.
        
        Returns:
            Current authentication token
        """
        if self._token is None:
            self._token = await self.authenticate()
        return self._token
    
    def invalidate_token(self) -> None:
        """Invalidate the current token, forcing re-authentication on next request."""
        self._token = None
        self._headers.clear()


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    
    def __init__(self, message: str, provider: str):
        self.message = message
        self.provider = provider
        super().__init__(f"Authentication failed for {provider}: {message}") 