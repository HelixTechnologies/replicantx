# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Payload formatter for different API formats.

This module provides utilities to format conversation data into different
API payload formats for maximum compatibility.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..models import Message, PayloadFormat, SessionPlacement
from .session_manager import SessionManager


class PayloadFormatter:
    """Formats conversation data into different API payload formats."""
    
    @staticmethod
    def format_payload(
        user_message: str,
        conversation_history: List[Message],
        payload_format: PayloadFormat,
        session_manager: Optional[SessionManager] = None,
        session_placement: SessionPlacement = SessionPlacement.BODY,
        session_variable_name: str = "session_id",
        timestamp: datetime = None
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Format conversation data into the specified payload format.
        
        Args:
            user_message: Current user message to send
            conversation_history: Full conversation history
            payload_format: Target payload format
            session_manager: Optional session manager for session-aware formats
            session_placement: Where to place session ID (header, body, or url)
            session_variable_name: Name of session variable in header/body
            timestamp: Optional timestamp (uses current time if not provided)
            
        Returns:
            Tuple of (payload_dict, session_headers_dict)
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Update session activity if session management is enabled
        if session_manager and session_manager.is_enabled():
            session_manager.update_activity()
        
        # Initialize session headers
        session_headers = {}
        
        if payload_format == PayloadFormat.OPENAI:
            payload = PayloadFormatter._format_openai(user_message, conversation_history)
        elif payload_format == PayloadFormat.SIMPLE:
            payload = PayloadFormatter._format_simple(user_message)
        elif payload_format == PayloadFormat.ANTHROPIC:
            payload = PayloadFormatter._format_anthropic(user_message, conversation_history)
        elif payload_format == PayloadFormat.LEGACY:
            payload = PayloadFormatter._format_legacy(user_message, conversation_history, timestamp)
        elif payload_format == PayloadFormat.OPENAI_SESSION:
            payload, session_headers = PayloadFormatter._format_openai_session(
                user_message, session_manager, session_placement, session_variable_name
            )
        elif payload_format == PayloadFormat.SIMPLE_SESSION:
            payload, session_headers = PayloadFormatter._format_simple_session(
                user_message, session_manager, session_placement, session_variable_name
            )
        elif payload_format == PayloadFormat.RESTFUL_SESSION:
            payload, session_headers = PayloadFormatter._format_restful_session(
                user_message, session_manager, session_placement, session_variable_name
            )
        else:
            raise ValueError(f"Unsupported payload format: {payload_format}")
        
        return payload, session_headers
    
    @staticmethod
    def _format_openai(user_message: str, conversation_history: List[Message]) -> Dict[str, Any]:
        """Format as OpenAI chat completion format.
        
        OpenAI format: {"messages": [{"role": "...", "content": "..."}]}
        """
        messages = []
        
        # Add conversation history
        for msg in conversation_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return {"messages": messages}
    
    @staticmethod
    def _format_simple(user_message: str) -> Dict[str, Any]:
        """Format as simple message-only format.
        
        Simple format: {"message": "..."}
        """
        return {"message": user_message}
    
    @staticmethod
    def _format_anthropic(user_message: str, conversation_history: List[Message]) -> Dict[str, Any]:
        """Format as Anthropic Claude format.
        
        Anthropic format: {"messages": [{"role": "...", "content": "..."}]}
        Note: Anthropic format is similar to OpenAI but may have different conventions
        """
        messages = []
        
        # Add conversation history
        for msg in conversation_history:
            messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Add current user message
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return {"messages": messages}
    
    @staticmethod
    def _format_legacy(user_message: str, conversation_history: List[Message], timestamp: datetime) -> Dict[str, Any]:
        """Format as legacy ReplicantX format (backward compatibility).
        
        Legacy format: {
            "message": "...",
            "timestamp": "...",
            "conversation_history": [{"role": "...", "content": "..."}]
        }
        """
        # Convert conversation history to legacy format
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in conversation_history
        ]
        
        return {
            "message": user_message,
            "timestamp": timestamp.isoformat(),
            "conversation_history": history
        }
    
    @staticmethod
    def _format_openai_session(
        user_message: str, 
        session_manager: Optional[SessionManager],
        session_placement: SessionPlacement,
        session_variable_name: str
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Format as OpenAI session-aware format.
        
        OpenAI session format: {"session_id": "...", "message": "..."} or header-based
        """
        if not session_manager or not session_manager.is_enabled():
            raise ValueError("Session-aware format requires enabled session manager")
        
        payload = {"message": user_message}
        session_headers = {}
        
        if session_placement == SessionPlacement.HEADER:
            session_headers[session_variable_name] = session_manager.session_id
        elif session_placement == SessionPlacement.BODY:
            payload[session_variable_name] = session_manager.session_id
        elif session_placement == SessionPlacement.URL:
            # URL placement is handled separately in get_session_url
            pass
        
        return payload, session_headers
    
    @staticmethod
    def _format_simple_session(
        user_message: str, 
        session_manager: Optional[SessionManager],
        session_placement: SessionPlacement,
        session_variable_name: str
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Format as simple session-aware format.
        
        Simple session format: {"conversation_id": "...", "message": "..."} or header-based
        """
        if not session_manager or not session_manager.is_enabled():
            raise ValueError("Session-aware format requires enabled session manager")
        
        payload = {"message": user_message}
        session_headers = {}
        
        if session_placement == SessionPlacement.HEADER:
            session_headers[session_variable_name] = session_manager.session_id
        elif session_placement == SessionPlacement.BODY:
            payload[session_variable_name] = session_manager.session_id
        elif session_placement == SessionPlacement.URL:
            # URL placement is handled separately in get_session_url
            pass
        
        return payload, session_headers
    
    @staticmethod
    def _format_restful_session(
        user_message: str, 
        session_manager: Optional[SessionManager],
        session_placement: SessionPlacement,
        session_variable_name: str
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Format as RESTful session-aware format.
        
        RESTful session format: {"message": "..."} (session ID goes in URL or header)
        """
        if not session_manager or not session_manager.is_enabled():
            raise ValueError("Session-aware format requires enabled session manager")
        
        payload = {"message": user_message}
        session_headers = {}
        
        if session_placement == SessionPlacement.HEADER:
            session_headers[session_variable_name] = session_manager.session_id
        elif session_placement == SessionPlacement.BODY:
            payload[session_variable_name] = session_manager.session_id
        elif session_placement == SessionPlacement.URL:
            # URL placement is handled separately in get_session_url
            pass
        
        return payload, session_headers
    
    @staticmethod
    def get_session_url(
        base_url: str, 
        session_manager: Optional[SessionManager], 
        payload_format: PayloadFormat,
        session_placement: SessionPlacement = SessionPlacement.BODY
    ) -> str:
        """Get the URL for session-aware requests.
        
        Args:
            base_url: Base API URL
            session_manager: Session manager instance
            payload_format: Payload format being used
            session_placement: Where session ID should be placed
            
        Returns:
            Formatted URL with session ID if applicable
        """
        if not session_manager or not session_manager.is_enabled():
            return base_url
        
        if (payload_format == PayloadFormat.RESTFUL_SESSION and 
            session_placement == SessionPlacement.URL):
            # For RESTful format with URL placement, session ID goes in the URL path
            return f"{base_url.rstrip('/')}/conversations/{session_manager.session_id}/messages"
        else:
            # For other formats or placements, session ID goes in payload or headers
            return base_url 