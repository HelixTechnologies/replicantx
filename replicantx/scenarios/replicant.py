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

from ..models import ReplicantConfig, Message, GoalEvaluationResult, GoalEvaluationMode
from ..tools.http_client import HTTPResponse


class ConversationState(BaseModel):
    """Current state of the conversation."""
    model_config = {"extra": "forbid"}
    
    turn_count: int = Field(0, description="Current turn number")
    goal_achieved: bool = Field(False, description="Whether the goal has been achieved")
    conversation_history: List[Message] = Field(default_factory=list, description="Full conversation history")
    extracted_info: Dict[str, Any] = Field(default_factory=dict, description="Information extracted from the conversation")
    goal_evaluation_result: Optional[GoalEvaluationResult] = Field(None, description="Latest goal evaluation result")


class GoalEvaluator(BaseModel):
    """Evaluates whether conversation goals have been achieved using different strategies."""
    model_config = {"extra": "forbid"}
    
    mode: GoalEvaluationMode = Field(..., description="Evaluation mode")
    model_name: Optional[str] = Field(None, description="Model for intelligent evaluation")
    custom_prompt: Optional[str] = Field(None, description="Custom evaluation prompt")
    completion_keywords: List[str] = Field(..., description="Keywords for keyword-based evaluation")
    
    @classmethod
    def create(cls, config: ReplicantConfig) -> "GoalEvaluator":
        """Create a GoalEvaluator from ReplicantConfig.
        
        Args:
            config: Replicant configuration
            
        Returns:
            Configured GoalEvaluator
        """
        model_name = config.goal_evaluation_model or config.llm.model
        
        return cls(
            mode=config.goal_evaluation_mode,
            model_name=model_name,
            custom_prompt=config.goal_evaluation_prompt,
            completion_keywords=config.completion_keywords
        )
    
    async def evaluate_goal_completion(
        self, 
        goal: str, 
        conversation_history: List[Message], 
        facts: Dict[str, Any]
    ) -> GoalEvaluationResult:
        """Evaluate whether the conversation goal has been achieved.
        
        Args:
            goal: The goal to evaluate
            conversation_history: Full conversation history
            facts: Available facts for context
            
        Returns:
            Goal evaluation result
        """
        if self.mode == GoalEvaluationMode.KEYWORDS:
            return self._evaluate_with_keywords(goal, conversation_history)
        elif self.mode == GoalEvaluationMode.INTELLIGENT:
            return await self._evaluate_with_llm(goal, conversation_history, facts)
        elif self.mode == GoalEvaluationMode.HYBRID:
            return await self._evaluate_hybrid(goal, conversation_history, facts)
        else:
            raise ValueError(f"Unknown goal evaluation mode: {self.mode}")
    
    def _evaluate_with_keywords(
        self, 
        goal: str, 
        conversation_history: List[Message]
    ) -> GoalEvaluationResult:
        """Evaluate goal completion using keyword matching (legacy behavior).
        
        Args:
            goal: The goal to evaluate
            conversation_history: Full conversation history
            
        Returns:
            Goal evaluation result
        """
        # Check for completion keywords in recent API responses
        goal_achieved = False
        matched_keywords = []
        
        if conversation_history:
            recent_messages = conversation_history[-2:]  # Last 2 messages
            for message in recent_messages:
                if message.role == "assistant":
                    message_lower = message.content.lower()
                    for keyword in self.completion_keywords:
                        if keyword.lower() in message_lower:
                            goal_achieved = True
                            matched_keywords.append(keyword)
        
        reasoning = f"Keyword evaluation: {'Found' if goal_achieved else 'No'} completion keywords"
        if matched_keywords:
            reasoning += f" (matched: {', '.join(matched_keywords)})"
        
        return GoalEvaluationResult(
            goal_achieved=goal_achieved,
            confidence=1.0 if goal_achieved else 0.0,  # Keywords give binary confidence
            reasoning=reasoning,
            evaluation_method="keywords",
            fallback_used=False
        )
    
    async def _evaluate_with_llm(
        self, 
        goal: str, 
        conversation_history: List[Message], 
        facts: Dict[str, Any]
    ) -> GoalEvaluationResult:
        """Evaluate goal completion using LLM analysis.
        
        Args:
            goal: The goal to evaluate
            conversation_history: Full conversation history
            facts: Available facts for context
            
        Returns:
            Goal evaluation result
        """
        try:
            # Build evaluation prompt
            prompt = self._build_evaluation_prompt(goal, conversation_history, facts)
            
            # Create LLM agent for evaluation
            model = infer_model(self.model_name)
            agent = PydanticAgent(
                model=model,
                instructions="You are an expert at evaluating whether conversation goals have been achieved. Be precise and analytical.",
                model_settings={"temperature": 0.1, "max_tokens": 200}  # Low temperature for consistency
            )
            
            # Get evaluation
            result = await agent.run(prompt)
            response = result.output.strip()
            
            # Parse LLM response
            goal_achieved, confidence, reasoning = self._parse_llm_response(response)
            
            return GoalEvaluationResult(
                goal_achieved=goal_achieved,
                confidence=confidence,
                reasoning=reasoning,
                evaluation_method="intelligent",
                fallback_used=False
            )
            
        except Exception as e:
            # Return failure result if LLM evaluation fails
            return GoalEvaluationResult(
                goal_achieved=False,
                confidence=0.0,
                reasoning=f"LLM evaluation failed: {str(e)}",
                evaluation_method="intelligent",
                fallback_used=False
            )
    
    async def _evaluate_hybrid(
        self, 
        goal: str, 
        conversation_history: List[Message], 
        facts: Dict[str, Any]
    ) -> GoalEvaluationResult:
        """Evaluate goal completion using LLM with keyword fallback.
        
        Args:
            goal: The goal to evaluate
            conversation_history: Full conversation history
            facts: Available facts for context
            
        Returns:
            Goal evaluation result
        """
        # Try LLM evaluation first
        try:
            llm_result = await self._evaluate_with_llm(goal, conversation_history, facts)
            if llm_result.confidence > 0.5:  # Use LLM result if confident
                return llm_result
        except Exception:
            pass
        
        # Fall back to keyword evaluation
        keyword_result = self._evaluate_with_keywords(goal, conversation_history)
        keyword_result.evaluation_method = "hybrid"
        keyword_result.fallback_used = True
        keyword_result.reasoning = f"LLM evaluation uncertain, using keyword fallback: {keyword_result.reasoning}"
        
        return keyword_result
    
    def _build_evaluation_prompt(
        self, 
        goal: str, 
        conversation_history: List[Message], 
        facts: Dict[str, Any]
    ) -> str:
        """Build the evaluation prompt for LLM analysis.
        
        Args:
            goal: The goal to evaluate
            conversation_history: Full conversation history
            facts: Available facts for context
            
        Returns:
            Formatted evaluation prompt
        """
        if self.custom_prompt:
            # Use custom prompt with variable substitution
            return self.custom_prompt.format(
                goal=goal,
                facts=json.dumps(facts, indent=2),
                conversation=self._format_conversation_for_prompt(conversation_history)
            )
        
        # Default evaluation prompt
        prompt = f"""Given this conversation goal: "{goal}"

User facts: {json.dumps(facts, indent=2)}

Recent conversation history:
{self._format_conversation_for_prompt(conversation_history[-6:])}

Has the goal been definitively achieved? Consider:
1. Has the user received confirmation that the action was completed?
2. Are there concrete indicators of success (confirmation numbers, bookings, etc.)?
3. Distinguish between promises ("I will do this") vs accomplishments ("This is done")
4. Look for specific completion indicators, not just polite acknowledgments

Respond in this exact format:
RESULT: [ACHIEVED or NOT_ACHIEVED]
CONFIDENCE: [0.0 to 1.0]
REASONING: [Brief explanation of your decision]"""

        return prompt
    
    def _format_conversation_for_prompt(self, messages: List[Message]) -> str:
        """Format conversation history for the evaluation prompt.
        
        Args:
            messages: List of messages to format
            
        Returns:
            Formatted conversation string
        """
        formatted = []
        for msg in messages:
            role = "User" if msg.role == "user" else "Assistant"
            formatted.append(f"{role}: {msg.content}")
        return "\n".join(formatted)
    
    def _parse_llm_response(self, response: str) -> Tuple[bool, float, str]:
        """Parse LLM evaluation response.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Tuple of (goal_achieved, confidence, reasoning)
        """
        lines = response.strip().split('\n')
        
        goal_achieved = False
        confidence = 0.5
        reasoning = "Could not parse LLM response"
        
        for line in lines:
            line = line.strip()
            if line.startswith('RESULT:'):
                result_text = line.replace('RESULT:', '').strip().upper()
                goal_achieved = result_text == 'ACHIEVED'
            elif line.startswith('CONFIDENCE:'):
                try:
                    confidence = float(line.replace('CONFIDENCE:', '').strip())
                    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
                except ValueError:
                    confidence = 0.5
            elif line.startswith('REASONING:'):
                reasoning = line.replace('REASONING:', '').strip()
        
        return goal_achieved, confidence, reasoning


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
            # Get current date and time
            current_datetime = datetime.now()
            date_str = current_datetime.strftime("%A, %B %d, %Y")
            time_str = current_datetime.strftime("%I:%M %p %Z")
            
            # Prepare context with facts AND conversation history
            context = f"Current date and time: {date_str} at {time_str}\n\n"
            context += f"Available facts: {json.dumps(self.facts, indent=2)}\n\n"
            
            # Add conversation history for context
            if conversation_state.conversation_history:
                context += "Conversation history:\n"
                for msg in conversation_state.conversation_history[-6:]:  # Last 6 messages
                    context += f"- {msg.role}: {msg.content}\n"
                context += "\n"
            
            context += f"Current API message: {api_message}\n\n"
            context += "Please generate a natural response as a user working toward your goal. "
            context += "Use the available facts when appropriate, and respond naturally to the API's question or statement. "
            context += "You know the current date and time, so you can reference it when relevant to the conversation."
            
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
    goal_evaluator: GoalEvaluator = Field(..., description="Goal evaluation utility")
    
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
        
        goal_evaluator = GoalEvaluator.create(config)
        
        return cls(
            config=config,
            response_generator=response_generator,
            goal_evaluator=goal_evaluator
        )
    
    async def should_continue_conversation(self) -> bool:
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
        
        # Evaluate goal completion using the configured method
        if self.state.conversation_history:
            evaluation_result = await self.goal_evaluator.evaluate_goal_completion(
                goal=self.config.goal,
                conversation_history=self.state.conversation_history,
                facts=self.config.facts
            )
            
            # Store evaluation result for reporting
            self.state.goal_evaluation_result = evaluation_result
            
            if evaluation_result.goal_achieved:
                self.state.goal_achieved = True
                return False
        
        return True
    
    def get_initial_message(self) -> str:
        """Get the initial message to start the conversation.
        
        Returns:
            Initial message
        """
        return self.config.initial_message
    
    async def process_api_response(self, api_response: str, triggering_message: Optional[str] = None) -> str:
        """Process an API response and generate the next user message.
        
        Args:
            api_response: Response from the API
            triggering_message: The user message that triggered this API response (for initial message)
            
        Returns:
            Next user message
        """
        # Add the triggering user message if this is the first response
        if triggering_message:
            user_trigger_message = Message(
                role="user",
                content=triggering_message,
                timestamp=datetime.now()
            )
            self.state.conversation_history.append(user_trigger_message)
        
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
        summary = {
            "total_turns": self.state.turn_count,
            "goal_achieved": self.state.goal_achieved,
            "conversation_length": len(self.state.conversation_history),
            "facts_used": self._count_facts_used(),
            "goal": self.config.goal,
        }
        
        # Add goal evaluation details if available
        if self.state.goal_evaluation_result:
            summary.update({
                "goal_evaluation_method": self.state.goal_evaluation_result.evaluation_method,
                "goal_evaluation_confidence": self.state.goal_evaluation_result.confidence,
                "goal_evaluation_reasoning": self.state.goal_evaluation_result.reasoning,
                "goal_evaluation_fallback_used": self.state.goal_evaluation_result.fallback_used,
            })
        
        return summary
    
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