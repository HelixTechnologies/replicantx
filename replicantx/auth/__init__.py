# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Authentication module for ReplicantX.

This module provides authentication providers for different services including
Supabase, JWT, and no-auth options.
"""

from .base import AuthBase
from .supabase import SupabaseAuth
from .jwt import JWTAuth
from .noop import NoopAuth
from .magic_link import SupabaseMagicLinkAuth

__all__ = [
    "AuthBase",
    "SupabaseAuth",
    "JWTAuth",
    "NoopAuth",
    "SupabaseMagicLinkAuth",
    "create_auth_provider",
]


def create_auth_provider(auth_config):
    """
    Factory function to create authentication providers.

    Args:
        auth_config: AuthConfig instance

    Returns:
        AuthBase subclass instance

    Raises:
        ValueError: If auth provider is not supported
    """
    from replicantx.models import AuthProvider

    provider = auth_config.provider

    if provider == AuthProvider.SUPABASE:
        return SupabaseAuth(auth_config)
    elif provider == AuthProvider.SUPABASE_MAGIC_LINK:
        return SupabaseMagicLinkAuth(auth_config)
    elif provider == AuthProvider.JWT:
        return JWTAuth(auth_config)
    elif provider == AuthProvider.NOOP:
        return NoopAuth(auth_config)
    else:
        raise ValueError(f"Unsupported auth provider: {provider}") 