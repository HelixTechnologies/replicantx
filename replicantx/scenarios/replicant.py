# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Pydantic-based Replicant agent for intelligent conversation with APIs.

This module provides a Replicant agent that can converse with APIs using
configurable facts and system prompts to achieve specific goals.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from pydantic import BaseModel, Field
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models import infer_model

from ..models import ReplicantConfig, Message
from ..tools.http_client import HTTPResponse


class ConversationState(BaseModel):
    """Current state of the conversation."""
    model_config = {"extra": "forbid"}
    
    turn_count: int = Field(0, description="Current turn number")
    goal_achieved: bool = Field(False, description="Whether the goal has been achieved")
    conversation_history: List[Message] = Field(default_factory=list, description="Full conversation history")
    extracted_info: Dict[str, Any] = Field(default_factory=dict, description="Information extracted from the conversation")


class ResponseGenerator(BaseModel):
    """Generates responses using PydanticAI agent with system prompt and available facts."""
    model_config = {"extra": "forbid"}
    
    model_name: str = Field(..., description="PydanticAI model name")
    system_prompt: str = Field(..., description="System prompt for response generation")
    model_settings: Dict[str, Any] = Field(default_factory=dict, description="Model settings")
    facts: Dict[str, Any] = Field(..., description="Available facts")
    
    def _create_agent(self) -> PydanticAgent:
        """Create a PydanticAI agent instance."""
        from pydantic_ai.models import infer_model
        
        model = infer_model(self.model_name)
        
        return PydanticAgent(
            model=model,
            instructions=self.system_prompt,
            model_settings=self.model_settings if self.model_settings else None
        )
    
    async def generate_response(self, api_message: str, conversation_state: ConversationState) -> str:
        """Generate a response to an API message using PydanticAI.
        
        Args:
            api_message: Message from the API
            conversation_state: Current conversation state
            
        Returns:
            Generated response
        """
        try:
            # Prepare context with facts AND conversation history
            context = f"Available facts: {json.dumps(self.facts, indent=2)}\n\n"
            
            # Add conversation history for context
            if conversation_state.conversation_history:
                context += "Conversation history:\n"
                for msg in conversation_state.conversation_history[-6:]:  # Last 6 messages
                    context += f"- {msg.role}: {msg.content}\n"
                context += "\n"
            
            context += f"Current API message: {api_message}\n\n"
            context += "Please generate a natural response as a user working toward your goal. "
            context += "Use the available facts when appropriate, and respond naturally to the API's question or statement."
            
            # Create and use PydanticAI agent
            agent = self._create_agent()
            result = await agent.run(context)
            
            return result.output
            
        except Exception as e:
            # Fallback to simple response if LLM fails
            print(f"PydanticAI generation failed: {e}")
            return self._generate_fallback_response(api_message, conversation_state)
    
    def _generate_fallback_response(self, api_message: str, conversation_state: ConversationState) -> str:
        """Generate a simple fallback response when LLM fails.
        
        Args:
            api_message: Message from the API
            conversation_state: Current conversation state
            
        Returns:
            Simple fallback response
        """
        api_lower = api_message.lower()
        
        # Very simple fallback responses
        if any(word in api_lower for word in ["hello", "hi", "welcome", "start"]):
            return "Hello! I'd like to get started with my request."
        elif any(word in api_lower for word in ["help", "assist"]):
            return "Yes, I'd appreciate your help with this."
        elif any(word in api_lower for word in ["confirm", "correct", "right"]):
            return "Yes, that sounds correct."
        elif "?" in api_message:
            return "I'm not sure about that. Could you help me with it?"
        else:
            return "I understand. Let's continue."


class ReplicantAgent(BaseModel):
    """Pydantic-based Replicant agent for intelligent conversation."""
    model_config = {"extra": "forbid"}
    
    config: ReplicantConfig = Field(..., description="Replicant configuration")
    state: ConversationState = Field(default_factory=ConversationState, description="Current conversation state")
    response_generator: ResponseGenerator = Field(..., description="Response generation utility")
    
    @classmethod
    def create(cls, config: ReplicantConfig) -> "ReplicantAgent":
        """Create a new Replicant agent.
        
        Args:
            config: Replicant configuration
            
        Returns:
            Configured Replicant agent
        """
        # Build model settings
        model_settings = {}
        if config.llm.temperature is not None:
            model_settings["temperature"] = config.llm.temperature
        if config.llm.max_tokens is not None:
            model_settings["max_tokens"] = config.llm.max_tokens
        
        response_generator = ResponseGenerator(
            model_name=config.llm.model,
            system_prompt=config.system_prompt,
            model_settings=model_settings,
            facts=config.facts
        )
        
        return cls(
            config=config,
            response_generator=response_generator
        )
    
    def should_continue_conversation(self) -> bool:
        """Determine if the conversation should continue.
        
        Returns:
            True if conversation should continue, False if complete
        """
        # Check turn limit
        if self.state.turn_count >= self.config.max_turns:
            return False
        
        # Check if goal is already marked as achieved
        if self.state.goal_achieved:
            return False
        
        # Check for completion keywords in recent API responses
        if self.state.conversation_history:
            recent_messages = self.state.conversation_history[-2:]  # Last 2 messages
            for message in recent_messages:
                if message.role == "assistant":
                    message_lower = message.content.lower()
                    if any(keyword in message_lower for keyword in self.config.completion_keywords):
                        self.state.goal_achieved = True
                        return False
        
        return True
    
    def get_initial_message(self) -> str:
        """Get the initial message to start the conversation.
        
        Returns:
            Initial message
        """
        return self.config.initial_message
    
    async def process_api_response(self, api_response: str) -> str:
        """Process an API response and generate the next user message.
        
        Args:
            api_response: Response from the API
            
        Returns:
            Next user message
        """
        # Add API response to conversation history
        api_message = Message(
            role="assistant",
            content=api_response,
            timestamp=datetime.now()
        )
        self.state.conversation_history.append(api_message)
        
        # Generate response using PydanticAI
        user_response = await self.response_generator.generate_response(api_response, self.state)
        
        # Add user response to conversation history
        user_message = Message(
            role="user",
            content=user_response,
            timestamp=datetime.now()
        )
        self.state.conversation_history.append(user_message)
        
        # Increment turn count
        self.state.turn_count += 1
        
        return user_response
    
    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get a summary of the conversation.
        
        Returns:
            Conversation summary
        """
        return {
            "total_turns": self.state.turn_count,
            "goal_achieved": self.state.goal_achieved,
            "conversation_length": len(self.state.conversation_history),
            "facts_used": self._count_facts_used(),
            "goal": self.config.goal,
        }
    
    def _count_facts_used(self) -> int:
        """Count how many facts were used in the conversation.
        
        Returns:
            Number of facts mentioned
        """
        facts_mentioned = set()
        
        for message in self.state.conversation_history:
            if message.role == "user":
                for fact_key, fact_value in self.config.facts.items():
                    if str(fact_value).lower() in message.content.lower():
                        facts_mentioned.add(fact_key)
        
        return len(facts_mentioned) 