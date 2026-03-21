# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Browser mode scenario runner for ReplicantX agent-level scenarios.

Uses a vision-capable LLM to observe the page (screenshot + DOM elements)
and decide what action to take each turn — filling forms, clicking buttons,
sending chat messages, etc.
"""

import asyncio
import base64
import json
from typing import Optional, List
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import infer_model

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
    GoalEvidenceMode,
)
from replicantx.auth.base import AuthBase
from replicantx.tools.browser import (
    BrowserAutomationDriver,
    ArtifactManager,
)


class PlannedAction(BaseModel):
    """Structured output from the planner LLM."""

    reasoning: str = Field(
        ..., description="Brief reasoning for why this action was chosen"
    )
    action_type: str = Field(
        ...,
        description=(
            "One of: click, fill, send_chat, press, wait, scroll, navigate"
        ),
    )
    target: Optional[str] = Field(
        None,
        description="Element ID (the number in square brackets) for click or fill",
    )
    value: Optional[str] = Field(
        None,
        description="Text value for fill, send_chat, or the key name for press",
    )
    url: Optional[str] = Field(
        None, description="URL for navigate action only"
    )


class BrowserScenarioRunner:
    """
    Runner for browser mode agent scenarios.

    Orchestrates browser automation with Playwright, using a vision-capable
    PydanticAI agent to observe pages and decide actions each turn.
    """

    def __init__(
        self,
        config: ScenarioConfig,
        auth_provider: AuthBase,
        debug: bool = False,
        watch: bool = False,
        verbose: bool = False,
    ):
        self.config = config
        self.auth_provider = auth_provider
        self.debug = debug
        self.watch = watch
        self.verbose = verbose

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

        self.browser_driver: Optional[BrowserAutomationDriver] = None
        self.artifact_manager: Optional[ArtifactManager] = None

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> ScenarioReport:
        start_time = datetime.now()
        passed = False
        error = None
        justification = ""

        try:
            if self.watch:
                print(f"\n🌐 BROWSER MODE - Starting scenario: {self.config.name}")
                print(f"🎯 Goal: {self.replicant_config.goal}")
                print(f"📍 URL: {self.browser_config.start_url}\n")

            self.artifact_manager = ArtifactManager(
                artifacts_dir="artifacts",
                scenario_name=self.config.name.replace(" ", "_").replace("/", "_"),
                trace_mode=self.browser_config.trace,
                config_screenshot_each_turn=self.browser_config.screenshot_on_each_turn,
                debug=self.debug,
            )

            self.browser_driver = BrowserAutomationDriver(
                config=self.browser_config,
                artifact_manager=self.artifact_manager,
                debug=self.debug,
            )

            await self.browser_driver.start()

            if hasattr(self.auth_provider, "set_browser_context"):
                self.auth_provider.set_browser_context(self.browser_driver.get_context())

            await self.auth_provider.authenticate()

            if hasattr(self.auth_provider, "generated_email") and self.auth_provider.generated_email:
                self.replicant_config.facts["email"] = self.auth_provider.generated_email

            self.current_observation = await self.browser_driver.goto(
                self.browser_config.start_url
            )

            # --- observe → plan → act loop (no hardcoded first action) ---
            turn = 0
            initial_message_sent = False

            while turn < self.replicant_config.max_turns:
                if self.watch:
                    print(f"\n{'─' * 50}")
                    print(f"📍 Turn {turn + 1}/{self.replicant_config.max_turns}")
                    print(f"{'─' * 50}")

                # Plan next action using LLM with screenshot + DOM
                action = await self._plan_next_action(initial_message_sent)

                if not action:
                    error = "Planner could not decide on an action"
                    if self.watch:
                        print(f"⚠️  {error}")
                    break

                if action.action_type == "send_chat":
                    initial_message_sent = True

                # Execute the action
                result = await self._execute_action_turn(action, turn)

                if not result.success:
                    if self.watch:
                        print(f"❌ Action failed: {result.message}")
                    # Don't break — let the planner try something else
                    turn += 1
                    continue

                # Check for stuck loop
                if self._detect_stuck_loop():
                    error = "Detected stuck loop (repeated actions with no change)"
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

                turn += 1

            if not passed and not error:
                justification = self._generate_justification(goal_achieved=False)
                if self.watch:
                    print(f"\n⏱️  Max turns reached without achieving goal")

        except Exception as e:
            error = str(e)
            if self.debug:
                import traceback
                traceback.print_exc()

        finally:
            if self.browser_driver:
                await self.browser_driver.stop()

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        passed_steps = sum(1 for r in self.step_results if r.passed)

        return ScenarioReport(
            scenario_name=self.config.name,
            passed=passed,
            total_steps=len(self.step_results),
            passed_steps=passed_steps,
            failed_steps=len(self.step_results) - passed_steps,
            total_duration_ms=duration_ms,
            step_results=self.step_results,
            error=error,
            justification=justification,
            goal_evaluation_result=self.goal_evaluation_result,
            started_at=start_time,
            completed_at=end_time,
        )

    # ------------------------------------------------------------------
    # LLM-based planner
    # ------------------------------------------------------------------

    async def _plan_next_action(
        self, initial_message_sent: bool
    ) -> Optional[BrowserAction]:
        """
        Use a vision-capable LLM to decide the next browser action.

        Sends a screenshot + structured elements list and gets back a
        PlannedAction with structured output.
        """
        try:
            # Capture a fresh screenshot for the planner
            screenshot_bytes = await self.browser_driver.get_page().screenshot(
                type="png"
            )

            # Re-capture observation so the elements list matches what's on screen
            self.current_observation = await self.browser_driver.capture_observation()

            # Build the system instructions
            system_prompt = self._build_planner_system_prompt(initial_message_sent)

            # Build the user message (elements list + action history)
            user_text = self._build_planner_user_message()

            # Resolve model
            model_name = (
                self.browser_config.planner_model
                or self.replicant_config.llm.model
            )
            model = infer_model(model_name)

            agent: Agent[None, PlannedAction] = Agent(
                model=model,
                output_type=PlannedAction,
                instructions=system_prompt,
                model_settings={"max_tokens": 1000},
            )

            if self.verbose:
                print(f"\n🤖 Planner model: {model_name}")
                print(f"   Elements: {len(self.current_observation.interactive_elements)}")
                print(f"   System prompt length: {len(system_prompt)}")

            result = await agent.run(
                [
                    user_text,
                    BinaryContent(data=screenshot_bytes, media_type="image/png"),
                ]
            )

            planned = result.output

            if self.watch:
                print(f"🧠 Plan: {planned.reasoning}")
                print(f"   → {planned.action_type}", end="")
                if planned.target:
                    print(f" [element {planned.target}]", end="")
                if planned.value:
                    val_preview = planned.value[:60] + ("…" if len(planned.value) > 60 else "")
                    print(f" = \"{val_preview}\"", end="")
                print()

            return BrowserAction(
                action_type=planned.action_type,
                target=planned.target,
                value=planned.value,
                url=planned.url,
            )

        except Exception as e:
            if self.debug:
                import traceback
                traceback.print_exc()
            if self.watch:
                print(f"⚠️  Planner error: {e}")
            return None

    def _build_planner_system_prompt(self, initial_message_sent: bool) -> str:
        facts_str = json.dumps(self.replicant_config.facts, indent=2)
        current_date = datetime.now().strftime("%A, %B %d, %Y")

        lines = [
            f"You are a browser automation agent. Your goal: {self.replicant_config.goal}",
            "",
            f"Today's date: {current_date}",
            "",
            f"Facts you know:\n{facts_str}",
            "",
            self.replicant_config.system_prompt,
            "",
            "You will receive a screenshot of the current page and a list of interactive elements.",
            "Choose ONE action per turn. Available action types:",
            "",
            "  click   — click an element (set target to the element ID number)",
            "  fill    — clear a field and type text (set target to element ID, value to the text)",
            "  send_chat — type a message in the chat input and press Enter (set value to the message)",
            "  press   — press a keyboard key (set value to the key, e.g. 'Enter', 'Escape', 'Tab')",
            "  wait    — wait for the page to update (no parameters needed)",
            "  scroll  — scroll the page (set value to 'up' or 'down')",
            "  navigate — go to a URL (set url to the destination)",
            "",
            "Important rules:",
            "- Look at the SCREENSHOT to understand what the page shows.",
            "- If you see a form (login, onboarding, profile, etc.), fill it out step by step.",
            "- If the page has a chat interface and you're ready to chat, use send_chat.",
            "- Don't repeat the same failing action — try something different.",
            "- For fill actions, use the element ID from the elements list.",
            "- For click actions, use the element ID from the elements list.",
            "- DROPDOWNS / SELECT BOXES: For dropdown or type-ahead select fields (like category, country, currency),",
            "  use the 'fill' action with the dropdown's element ID and the desired value.",
            "  The fill action will type the text and automatically select the matching option from the dropdown.",
            "  Do NOT try to click the dropdown then separately click an option — just use fill.",
            "- If a dropdown option is visible in the elements list (role='option'), you can click it directly.",
        ]

        if not initial_message_sent and self.replicant_config.initial_message:
            lines.extend([
                "",
                "When you reach a chat interface, your first message should be:",
                f'  "{self.replicant_config.initial_message}"',
            ])

        return "\n".join(lines)

    def _build_planner_user_message(self) -> str:
        lines = []

        # Current page info
        obs = self.current_observation
        if obs:
            lines.append(f"Current URL: {obs.url}")
            lines.append(f"Page title: {obs.title}")
            lines.append("")

            # Interactive elements
            if obs.interactive_elements:
                lines.append("Interactive elements on this page:")
                for elem in obs.interactive_elements:
                    tag_hint = f" ({elem.tag_name})" if elem.tag_name else ""
                    lines.append(f"  [{elem.id}] {elem.role}{tag_hint}: {elem.name}")
            else:
                lines.append("No interactive elements detected.")
            lines.append("")

            # Visible text excerpt
            text_excerpt = obs.visible_text[:2000]
            lines.append(f"Visible text excerpt:\n{text_excerpt}")
            lines.append("")

        # Recent action history
        if self.action_history:
            lines.append("Recent actions:")
            for ah in self.action_history[-6:]:
                status = "✓" if ah["success"] else "✗"
                lines.append(f"  {status} {ah['action']}: {ah.get('detail', '')}")
            lines.append("")

        lines.append("Decide the next action. Look at the screenshot carefully.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    async def _execute_action_turn(
        self, action: BrowserAction, turn_index: int
    ) -> BrowserActionResult:
        if self.watch:
            if action.action_type == "send_chat":
                print(f"💬 Chat: {action.value}")
            elif action.action_type == "click":
                print(f"🖱️  Click: element {action.target}")
            elif action.action_type == "fill":
                print(f"⌨️  Fill: element {action.target} = {action.value}")
            elif action.action_type == "press":
                print(f"⌨️  Press: {action.value}")
            else:
                print(f"⚡ {action.action_type}")

        result = await self.browser_driver.perform(action, self.current_observation)

        if result.observation:
            self.current_observation = result.observation

        step_result = StepResult(
            step_index=turn_index,
            user_message=self._action_to_message(action),
            response=self._observation_to_response(result.observation),
            latency_ms=result.latency_ms,
            passed=result.success,
            error=result.error,
            timestamp=datetime.now(),
            action_type=action.action_type,
            action_summary=result.message,
            page_url=result.observation.url if result.observation else None,
            observation_excerpt=self._excerpt_observation(result.observation),
            artifact_paths=(
                {"screenshot": result.screenshot_path} if result.screenshot_path else {}
            ),
        )
        self.step_results.append(step_result)

        detail = ""
        if action.target:
            detail += f"element {action.target}"
        if action.value:
            detail += f" = {action.value[:40]}"

        self.action_history.append(
            {
                "action": action.action_type,
                "detail": detail.strip(),
                "success": result.success,
                "visible_text": (
                    result.observation.visible_text[:200] if result.observation else ""
                ),
            }
        )

        if not result.success and self.artifact_manager:
            screenshot_path = await self.artifact_manager.capture_failure_screenshot(
                self.browser_driver.get_page(), turn_index
            )
            if screenshot_path:
                step_result.artifact_paths["failure_screenshot"] = screenshot_path

        if self.watch:
            status = "✅" if result.success else "❌"
            print(f"{status} {result.message}")

        return result

    # ------------------------------------------------------------------
    # Goal evaluation (unchanged — uses existing GoalEvaluator)
    # ------------------------------------------------------------------

    async def _evaluate_goal(self) -> bool:
        from replicantx.scenarios.replicant import GoalEvaluator
        from replicantx.models import GoalEvidenceMode

        evaluator = GoalEvaluator.create(self.replicant_config, verbose=self.verbose)

        conversation_text = "\n".join(
            [
                f"Action: {r.action_summary or r.user_message}"
                for r in self.step_results
            ]
        )

        goal_evidence = self.browser_config.goal_evidence
        screenshot_path = None

        if goal_evidence in [GoalEvidenceMode.SCREENSHOT, GoalEvidenceMode.BOTH]:
            screenshot_path = await self.artifact_manager.capture_screenshot(
                self.browser_driver.get_page(),
                name=f"evaluation_turn_{len(self.step_results)}",
                force=True,
            )
        elif goal_evidence == GoalEvidenceMode.DOM_THEN_SCREENSHOT:
            screenshot_path = await self.artifact_manager.capture_screenshot(
                self.browser_driver.get_page(),
                name=f"evaluation_turn_{len(self.step_results)}",
                force=False,
            )

        self.goal_evaluation_result = await evaluator.evaluate_goal_completion(
            goal=self.replicant_config.goal,
            facts=self.replicant_config.facts,
            conversation=conversation_text,
            current_observation=self.current_observation,
            screenshot_path=screenshot_path,
            goal_evidence_mode=goal_evidence,
        )

        if self.watch and self.verbose:
            print(f"\n🎯 Goal Evaluation:")
            print(f"   Achieved: {self.goal_evaluation_result.goal_achieved}")
            print(f"   Confidence: {self.goal_evaluation_result.confidence:.2f}")
            print(f"   Method: {self.goal_evaluation_result.evaluation_method}")
            print(f"   Reasoning: {self.goal_evaluation_result.reasoning}")

        return self.goal_evaluation_result.goal_achieved

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _detect_stuck_loop(self) -> bool:
        if len(self.action_history) < 3:
            return False

        last = self.action_history[-3:]

        # Waiting for content is normal — require 5 consecutive waits
        # with no page change before calling it stuck
        if all(a["action"] == "wait" for a in last):
            if len(self.action_history) < 5:
                return False
            last5 = self.action_history[-5:]
            if not all(a["action"] == "wait" for a in last5):
                return False
            texts = {a.get("visible_text", "")[:200] for a in last5}
            return len(texts) == 1

        same_action = len({a["action"] for a in last}) == 1
        same_detail = len({a["detail"] for a in last}) == 1
        same_text = len({a.get("visible_text", "")[:200] for a in last}) == 1
        return same_action and same_detail and same_text

    def _action_to_message(self, action: BrowserAction) -> str:
        if action.action_type == "send_chat":
            return action.value or ""
        elif action.action_type == "click":
            return f"Click element {action.target or '?'}"
        elif action.action_type == "fill":
            return f"Fill element {action.target} with \"{action.value}\""
        elif action.action_type == "press":
            return f"Press {action.value}"
        elif action.action_type == "navigate":
            return f"Navigate to {action.url}"
        return f"Action: {action.action_type}"

    def _observation_to_response(self, obs: Optional[BrowserObservation]) -> str:
        if not obs:
            return "No observation"
        text = obs.visible_text[:500]
        if len(obs.visible_text) > 500:
            text += "..."
        return f"Page: {obs.title}\nURL: {obs.url}\n\n{text}"

    def _excerpt_observation(self, obs: Optional[BrowserObservation]) -> str:
        if not obs:
            return ""
        return f"{obs.title} - {obs.visible_text[:200]}..."

    def _generate_justification(self, goal_achieved: bool) -> str:
        if goal_achieved:
            j = f"Goal achieved: {self.replicant_config.goal}"
            if self.goal_evaluation_result:
                j += f"\nConfidence: {self.goal_evaluation_result.confidence:.2f}"
                j += f"\nReasoning: {self.goal_evaluation_result.reasoning}"
            return j

        j = f"Goal not achieved: {self.replicant_config.goal}\n"
        j += f"Completed {len(self.step_results)} turns without reaching goal."
        if self.goal_evaluation_result:
            j += f"\nLast confidence: {self.goal_evaluation_result.confidence:.2f}"
        return j
