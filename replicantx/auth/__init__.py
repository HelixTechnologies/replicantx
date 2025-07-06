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

__all__ = [
    "AuthBase",
    "SupabaseAuth", 
    "JWTAuth",
    "NoopAuth",
] 