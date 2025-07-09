# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Payload formatter for different API formats.

This module provides utilities to format conversation data into different
API payload formats for maximum compatibility.
"""

from datetime import datetime
from typing import Any, Dict, List

from ..models import Message, PayloadFormat


class PayloadFormatter:
    """Formats conversation data into different API payload formats."""
    
    @staticmethod
    def format_payload(
        user_message: str,
        conversation_history: List[Message],
        payload_format: PayloadFormat,
        timestamp: datetime = None
    ) -> Dict[str, Any]:
        """Format conversation data into the specified payload format.
        
        Args:
            user_message: Current user message to send
            conversation_history: Full conversation history
            payload_format: Target payload format
            timestamp: Optional timestamp (uses current time if not provided)
            
        Returns:
            Formatted payload dictionary
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        if payload_format == PayloadFormat.OPENAI:
            return PayloadFormatter._format_openai(user_message, conversation_history)
        elif payload_format == PayloadFormat.SIMPLE:
            return PayloadFormatter._format_simple(user_message)
        elif payload_format == PayloadFormat.ANTHROPIC:
            return PayloadFormatter._format_anthropic(user_message, conversation_history)
        elif payload_format == PayloadFormat.LEGACY:
            return PayloadFormatter._format_legacy(user_message, conversation_history, timestamp)
        else:
            raise ValueError(f"Unsupported payload format: {payload_format}")
    
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