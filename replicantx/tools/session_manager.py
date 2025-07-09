# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Session manager for ReplicantX conversation sessions.

This module provides session management utilities for maintaining
conversation state across multiple API requests.
"""

import os
import uuid
from datetime import datetime
from typing import Optional

from ..models import SessionMode, SessionFormat


class SessionManager:
    """Manages conversation session lifecycle and state."""
    
    def __init__(self, session_mode: SessionMode, session_id: Optional[str] = None, 
                 timeout_seconds: int = 300, session_format: SessionFormat = SessionFormat.UUID):
        """Initialize the session manager.
        
        Args:
            session_mode: How to handle session ID generation
            session_id: Fixed session ID (for FIXED mode)
            timeout_seconds: Session timeout in seconds
            session_format: Format for auto-generated session IDs
        """
        self.session_mode = session_mode
        self.timeout_seconds = timeout_seconds
        self.session_format = session_format
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        
        # Generate or set session ID based on mode
        self.session_id = self._initialize_session_id(session_id)
    
    def _initialize_session_id(self, session_id: Optional[str] = None) -> str:
        """Initialize session ID based on the session mode.
        
        Args:
            session_id: Fixed session ID (for FIXED mode)
            
        Returns:
            Session ID string
        """
        if self.session_mode == SessionMode.DISABLED:
            return None
        elif self.session_mode == SessionMode.AUTO:
            return self._generate_session_id()
        elif self.session_mode == SessionMode.FIXED:
            if not session_id:
                raise ValueError("Fixed session mode requires session_id to be provided")
            return session_id
        elif self.session_mode == SessionMode.ENV:
            env_session_id = os.getenv("REPLICANTX_SESSION_ID")
            if not env_session_id:
                raise ValueError("Environment session mode requires REPLICANTX_SESSION_ID environment variable")
            return env_session_id
        else:
            raise ValueError(f"Unsupported session mode: {self.session_mode}")
    
    def _generate_session_id(self) -> str:
        """Generate a session ID based on the configured format.
        
        Returns:
            Generated session ID string
        """
        if self.session_format == SessionFormat.REPLICANTX:
            return f"replicantx_{uuid.uuid4().hex[:8]}"
        elif self.session_format == SessionFormat.UUID:
            return str(uuid.uuid4())
        else:
            raise ValueError(f"Unsupported session format: {self.session_format}")
    
    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
    
    def is_expired(self) -> bool:
        """Check if the session has expired.
        
        Returns:
            True if session has expired, False otherwise
        """
        if self.session_mode == SessionMode.DISABLED:
            return False
        
        elapsed_seconds = (datetime.now() - self.last_activity).total_seconds()
        return elapsed_seconds > self.timeout_seconds
    
    def get_session_info(self) -> dict:
        """Get session information for debugging.
        
        Returns:
            Dictionary with session information
        """
        if self.session_mode == SessionMode.DISABLED:
            return {"session_mode": "disabled"}
        
        return {
            "session_id": self.session_id,
            "session_mode": self.session_mode.value,
            "session_format": self.session_format.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "timeout_seconds": self.timeout_seconds,
            "is_expired": self.is_expired(),
            "elapsed_seconds": (datetime.now() - self.last_activity).total_seconds()
        }
    
    def is_enabled(self) -> bool:
        """Check if session management is enabled.
        
        Returns:
            True if session management is enabled, False otherwise
        """
        return self.session_mode != SessionMode.DISABLED 