# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Browser mode scenario runner for ReplicantX agent-level scenarios.
"""

import asyncio
from typing import Optional, List
from datetime import datetime
from pydantic_ai import Agent

from replicantx.models import (
    ScenarioConfig,
    ScenarioReport,
    StepResult,
    ReplicantConfig,
    BrowserAction,
    BrowserActionResult,
    BrowserObservation,
    GoalEvaluationResult,
    InteractionMode,
)
from replicantx.auth.base import AuthBase
from replicantx.tools.browser import (
    BrowserAutomationDriver,
    ArtifactManager,
)
from replicantx.tools.browser.observation import detect_chat_input


class BrowserScenarioRunner:
    """
    Runner for browser mode agent scenarios.

    Orchestrates browser automation with Playwright, using a tool-using
    PydanticAI agent to decide actions and evaluate goals.
    """

    def __init__(
        self,
        config: ScenarioConfig,
        auth_provider: AuthBase,
        debug: bool = False,
        watch: bool = False,
        verbose: bool = False,
    ):
        """
        Initialize the browser scenario runner.

        Args:
            config: Scenario configuration
            auth_provider: Authentication provider
            debug: Whether to print debug information
            watch: Whether to print live conversation
            verbose: Whether to print verbose information
        """
        self.config = config
        self.auth_provider = auth_provider
        self.debug = debug
        self.watch = watch
        self.verbose = verbose

        # Validate configuration
        if config.level != "agent":
            raise ValueError("BrowserScenarioRunner only supports agent-level scenarios")

        if config.replicant.interaction_mode != InteractionMode.BROWSER:
            raise ValueError("BrowserScenarioRunner requires interaction_mode='browser'")

        self.replicant_config = config.replicant
        self.browser_config = config.replicant.browser

        # State
        self.step_results: List[StepResult] = []
        self.action_history: List[dict] = []
        self.current_observation: Optional[BrowserObservation] = None
        self.goal_evaluation_result: Optional[GoalEvaluationResult] = None

        # Browser and artifact manager
        self.browser_driver: Optional[BrowserAutomationDriver] = None
        self.artifact_manager: Optional[ArtifactManager] = None

        # PydanticAI agent for action selection
        self.planner_agent: Optional[Agent] = None

    async def run(self) -> ScenarioReport:
        """
        Run the browser scenario.

        Returns:
            ScenarioReport with results
        """
        start_time = datetime.now()
        passed = False
        error = None
        justification = ""

        try:
            if self.watch:
                print(f"\n🌐 BROWSER MODE - Starting scenario: {self.config.name}")
                print(f"🎯 Goal: {self.replicant_config.goal}")
                print(f"📍 URL: {self.browser_config.start_url}\n")

            # Initialize artifact manager
            self.artifact_manager = ArtifactManager(
                artifacts_dir="artifacts",
                scenario_name=self.config.name.replace(" ", "_").replace("/", "_"),
                trace_mode=self.browser_config.trace,
            )

            # Initialize browser driver
            self.browser_driver = BrowserAutomationDriver(
                config=self.browser_config,
                artifact_manager=self.artifact_manager,
                debug=self.debug,
            )

            # Start browser
            await self.browser_driver.start()

            # Set browser context for auth (if applicable)
            if hasattr(self.auth_provider, "set_browser_context"):
                self.auth_provider.set_browser_context(self.browser_driver.get_context())

            # Authenticate
            await self.auth_provider.authenticate()

            # Inject generated email into facts if using magic link
            if hasattr(self.auth_provider, "generated_email") and self.auth_provider.generated_email:
                self.replicant_config.facts["email"] = self.auth_provider.generated_email

            # Navigate to start URL
            self.current_observation = await self.browser_driver.goto(self.browser_config.start_url)

            # Create planner agent
            self.planner_agent = self._create_planner_agent()

            # Execute initial message (send chat)
            turn = 0
            action = BrowserAction(
                action_type="send_chat",
                value=self.replicant_config.initial_message,
            )

            # Main conversation loop
            while turn < self.replicant_config.max_turns:
                if self.watch:
                    print(f"\n[{' ' * 40}]")
                    print(f"📍 Turn {turn + 1}/{self.replicant_config.max_turns}")
                    print(f"[{' ' * 40}]")

                # Execute action
                result = await self._execute_action_turn(action, turn)

                if not result.success:
                    # Action failed
                    error = result.message
                    if self.watch:
                        print(f"❌ Action failed: {error}")
                    break

                # Check for stuck loop
                if self._detect_stuck_loop():
                    error = "Detected stuck loop (repeated actions)"
                    if self.watch:
                        print(f"⚠️  {error}")
                    break

                # Evaluate goal
                goal_achieved = await self._evaluate_goal()

                if goal_achieved:
                    passed = True
                    justification = self._generate_justification(goal_achieved=True)
                    if self.watch:
                        print(f"\n✅ GOAL ACHIEVED: {self.replicant_config.goal}")
                    break

                # Plan next action
                action = await self._plan_next_action()

                if not action:
                    # Agent couldn't decide on an action
                    error = "Agent couldn't decide on next action"
                    if self.watch:
                        print(f"⚠️  {error}")
                    break

                turn += 1

            if not passed and not error:
                # Max turns reached
                justification = self._generate_justification(goal_achieved=False)
                if self.watch:
                    print(f"\n⏱️  Max turns reached without achieving goal")

        except Exception as e:
            error = str(e)
            if self.debug:
                import traceback
                traceback.print_exc()

        finally:
            # Cleanup
            if self.browser_driver:
                await self.browser_driver.stop()

        # Generate report
        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000

        # Count passed/failed steps
        passed_steps = sum(1 for r in self.step_results if r.passed)
        failed_steps = len(self.step_results) - passed_steps

        report = ScenarioReport(
            scenario_name=self.config.name,
            passed=passed,
            total_steps=len(self.step_results),
            passed_steps=passed_steps,
            failed_steps=failed_steps,
            total_duration_ms=duration_ms,
            step_results=self.step_results,
            error=error,
            justification=justification,
            goal_evaluation_result=self.goal_evaluation_result,
            started_at=start_time,
            completed_at=end_time,
        )

        return report

    async def _execute_action_turn(self, action: BrowserAction, turn_index: int) -> BrowserActionResult:
        """
        Execute a single action turn.

        Args:
            action: Action to execute
            turn_index: Turn index

        Returns:
            BrowserActionResult
        """
        if self.watch:
            if action.action_type == "send_chat":
                print(f"💬 Chat: {action.value}")
            elif action.action_type == "click":
                print(f"🖱️  Click: {action.target}")
            elif action.action_type == "fill":
                print(f"⌨️  Fill: {action.target} = {action.value}")
            else:
                print(f"⚡ Action: {action.action_type}")

        # Execute action
        result = await self.browser_driver.perform(action, self.current_observation)

        # Update observation
        if result.observation:
            self.current_observation = result.observation

        # Create step result
        step_result = StepResult(
            step_index=turn_index,
            user_message=self._action_to_message(action),
            response=self._observation_to_response(result.observation),
            latency_ms=result.latency_ms,
            passed=result.success,
            error=result.error,
            timestamp=datetime.now(),
            # Browser-specific fields
            action_type=action.action_type,
            action_summary=result.message,
            page_url=result.observation.url if result.observation else None,
            observation_excerpt=self._excerpt_observation(result.observation),
            artifact_paths={"screenshot": result.screenshot_path} if result.screenshot_path else {},
        )

        self.step_results.append(step_result)

        # Track action history
        self.action_history.append({
            "action": action.action_type,
            "target": action.target,
            "value": action.value,
            "success": result.success,
            "visible_text": result.observation.visible_text if result.observation else "",
        })

        # Capture screenshot on failure
        if not result.success:
            screenshot_path = await self.artifact_manager.capture_failure_screenshot(
                self.browser_driver.get_page(),
                turn_index,
            )
            if screenshot_path:
                step_result.artifact_paths["failure_screenshot"] = screenshot_path

        if self.watch:
            status = "✅" if result.success else "❌"
            print(f"{status} {result.message}")

        return result

    async def _evaluate_goal(self) -> bool:
        """
        Evaluate if the goal has been achieved.

        Returns:
            True if goal achieved
        """
        from replicantx.scenarios.replicant import GoalEvaluator

        # Create goal evaluator
        evaluator = GoalEvaluator.create(self.replicant_config)

        # Prepare conversation context
        conversation_text = "\n".join([
            f"{'User' if i % 2 == 0 else 'Assistant'}: {r.user_message if i % 2 == 0 else r.response}"
            for i, r in enumerate(self.step_results)
        ])

        # Build evidence based on mode
        goal_evidence = self.browser_config.goal_evidence

        if goal_evidence in ["dom", "dom_then_screenshot", "both"]:
            # DOM-based evaluation
            self.goal_evaluation_result = await evaluator.evaluate_goal_completion(
                goal=self.replicant_config.goal,
                facts=self.replicant_config.facts,
                conversation=conversation_text,
                current_observation=self.current_observation,
            )

            # Check if we need screenshot fallback
            if goal_evidence == "dom_then_screenshot" and self.goal_evaluation_result.confidence < 0.5:
                # Fall back to screenshot evaluation
                # TODO: Implement screenshot evaluation
                pass

        return self.goal_evaluation_result.goal_achieved

    async def _plan_next_action(self) -> Optional[BrowserAction]:
        """
        Plan the next action using the LLM.

        Returns:
            Next action to take, or None if couldn't decide
        """
        # Build context for the planner
        context = self._build_planner_context()

        # For now, use a simple heuristic-based approach
        # In a full implementation, this would use a PydanticAI agent with tools

        # Check if there are interactive elements
        if self.current_observation and self.current_observation.interactive_elements:
            # Check if any element looks like a good click target
            # (e.g., button with relevant text)
            for elem in self.current_observation.interactive_elements[:5]:  # Check top 5
                # Simple heuristic: if element contains goal-related keywords
                if any(keyword in elem.name.lower() for keyword in self.replicant_config.completion_keywords):
                    return BrowserAction(action_type="click", target=elem.id)

        # Default: send a chat message
        # In a full implementation, the LLM would generate the message
        return None  # For now, return None to stop

    def _create_planner_agent(self) -> Agent:
        """
        Create the PydanticAI planner agent.

        Returns:
            PydanticAI Agent instance
        """
        # For now, return a mock agent
        # In a full implementation, this would create a proper tool-using agent
        return None

    def _build_planner_context(self) -> str:
        """
        Build context for the planner agent.

        Returns:
            Context string
        """
        lines = [
            f"Goal: {self.replicant_config.goal}",
            f"Facts: {self.replicant_config.facts}",
            f"Current URL: {self.current_observation.url if self.current_observation else 'Unknown'}",
            "",
            "Recent actions:",
        ]

        for action_info in self.action_history[-6:]:
            lines.append(f"  - {action_info['action']}: {action_info.get('target') or action_info.get('value') or ''} ({'success' if action_info['success'] else 'failed'})")

        if self.current_observation:
            lines.extend([
                "",
                "Current page:",
                f"  Title: {self.current_observation.title}",
                f"  Visible text: {self.current_observation.visible_text[:500]}...",
                "",
                "Interactive elements:",
            ])
            for elem in self.current_observation.interactive_elements[:10]:
                lines.append(f"  - [{elem.id}] {elem.role}: {elem.name}")

        return "\n".join(lines)

    def _detect_stuck_loop(self) -> bool:
        """
        Detect if we're stuck in a loop.

        Returns:
            True if stuck loop detected
        """
        if len(self.action_history) < 3:
            return False

        # Check if last 3 actions are the same
        last_actions = self.action_history[-3:]
        if len(set(a["action"] for a in last_actions)) == 1:
            # Same action type repeated
            # Check if visible text hasn't changed much
            texts = [a.get("visible_text", "")[:200] for a in last_actions]
            if len(set(texts)) == 1:
                return True  # Same action, same content = stuck

        return False

    def _action_to_message(self, action: BrowserAction) -> str:
        """Convert action to user message string."""
        if action.action_type == "send_chat":
            return action.value or ""
        elif action.action_type == "click":
            return f"Click {action.target or 'element'}"
        elif action.action_type == "fill":
            return f"Fill {action.target} with {action.value}"
        elif action.action_type == "press":
            return f"Press {action.value}"
        elif action.action_type == "navigate":
            return f"Navigate to {action.url}"
        else:
            return f"Action: {action.action_type}"

    def _observation_to_response(self, observation: Optional[BrowserObservation]) -> str:
        """Convert observation to response string."""
        if not observation:
            return "No observation"

        # Return a summary
        lines = [
            f"Page: {observation.title}",
            f"URL: {observation.url}",
            "",
            observation.visible_text[:500] + "..." if len(observation.visible_text) > 500 else observation.visible_text,
        ]

        return "\n".join(lines)

    def _excerpt_observation(self, observation: Optional[BrowserObservation]) -> str:
        """Create an excerpt from observation."""
        if not observation:
            return ""

        return f"{observation.title} - {observation.visible_text[:200]}..."

    def _generate_justification(self, goal_achieved: bool) -> str:
        """Generate justification for the result."""
        if goal_achieved:
            justification = f"Goal achieved: {self.replicant_config.goal}"
            if self.goal_evaluation_result:
                justification += f"\nConfidence: {self.goal_evaluation_result.confidence:.2f}\n"
                justification += f"Reasoning: {self.goal_evaluation_result.reasoning}"
        else:
            justification = f"Goal not achieved: {self.replicant_config.goal}\n"
            justification += f"Completed {len(self.step_results)} turns without reaching goal."

            if self.goal_evaluation_result:
                justification += f"\nLast evaluation confidence: {self.goal_evaluation_result.confidence:.2f}"

        return justification
