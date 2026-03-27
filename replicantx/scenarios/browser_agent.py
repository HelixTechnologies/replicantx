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
import os
from typing import Any, Optional, List, Dict
from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, Field
from pydantic_ai import Agent, BinaryContent
from pydantic_ai.models import infer_model

from replicantx.prompts import load_prompt
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
    BrowserScenarioDiagnostics,
    BrowserIdentityContext,
    BrowserTurnDiagnostic,
    BrowserNetworkEvent,
    BrowserConsoleEvent,
    BrowserPageErrorEvent,
    BrowserWebSocketEvent,
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
            "One of: click, fill, send_chat, compose_chat, submit_chat, press, wait, scroll, navigate"
        ),
    )
    target: Optional[str] = Field(
        None,
        description="Element ID (the number in square brackets) for click or fill",
    )
    value: Optional[str] = Field(
        None,
        description="Text value for fill, send_chat, compose_chat, or the key name for press",
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
        llm_debug: bool = False,
    ):
        self.config = config
        self.auth_provider = auth_provider
        self.debug = debug
        self.watch = watch
        self.verbose = verbose
        self.llm_debug = llm_debug

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
        self.browser_diagnostics: Optional[BrowserScenarioDiagnostics] = None
        self._pending_planned_reasoning: Optional[str] = None
        self._first_party_hosts = self._build_first_party_hosts()
        self._wait_stuck_threshold_seconds = 20.0
        self._wait_stuck_min_consecutive_waits = 6

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> ScenarioReport:
        start_time = datetime.now()
        passed = False
        error = None
        justification = ""
        artifact_summary: Dict[str, Any] = {}

        self.browser_diagnostics = BrowserScenarioDiagnostics(
            scenario_name=self.config.name,
            goal=self.replicant_config.goal,
            start_url=self.browser_config.start_url,
            started_at=start_time,
            environment=os.getenv("REPLICANTX_ENVIRONMENT"),
        )

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
            self._attach_diagnostic_listeners()

            if hasattr(self.auth_provider, "set_browser_context"):
                self.auth_provider.set_browser_context(self.browser_driver.get_context())

            await self.auth_provider.authenticate()

            if hasattr(self.auth_provider, "generated_email") and self.auth_provider.generated_email:
                self.replicant_config.facts["email"] = self.auth_provider.generated_email

            self.current_observation = await self.browser_driver.goto(
                self.browser_config.start_url
            )
            await self._refresh_identity_context()

            # --- observe → plan → act loop (no hardcoded first action) ---
            turn = 0
            initial_message_sent = False

            while turn < self.replicant_config.max_turns:
                if self.watch:
                    print(f"\n{'─' * 50}")
                    print(f"📍 Turn {turn + 1}/{self.replicant_config.max_turns}")
                    print(f"{'─' * 50}")

                # Plan next action using LLM with screenshot + DOM
                self._llm_debug_turn = turn + 1
                action = await self._plan_next_action(initial_message_sent)

                if not action:
                    error = "Planner could not decide on an action"
                    if self.watch:
                        print(f"⚠️  {error}")
                    break

                if action.action_type in ("send_chat", "submit_chat"):
                    initial_message_sent = True

                # Execute the action
                result = await self._execute_action_turn(action, turn)
                await self._refresh_identity_context()

                # Check for stuck loop even after failed actions so we can stop
                # repeated retries with no useful state change.
                if self._detect_stuck_loop():
                    error = "Detected stuck loop (repeated actions with no change)"
                    if self.watch:
                        print(f"⚠️  {error}")
                    break

                if not result.success:
                    if self.watch:
                        print(f"❌ Action failed: {result.message}")
                    # Don't break — let the planner try something else
                    turn += 1
                    continue

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
            if self.artifact_manager:
                artifact_summary = self.artifact_manager.get_artifact_summary()

        end_time = datetime.now()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        passed_steps = sum(1 for r in self.step_results if r.passed)

        if self.browser_diagnostics:
            self.browser_diagnostics.completed_at = end_time
            self.browser_diagnostics.artifact_dir = artifact_summary.get("scenario_dir")
            self.browser_diagnostics.trace_path = artifact_summary.get("trace")

        return ScenarioReport(
            scenario_name=self.config.name,
            passed=passed,
            total_steps=len(self.step_results),
            passed_steps=passed_steps,
            failed_steps=len(self.step_results) - passed_steps,
            total_duration_ms=duration_ms,
            step_results=self.step_results,
            source_file=None,
            error=error,
            justification=justification,
            goal_evaluation_result=self.goal_evaluation_result,
            artifact_summary=artifact_summary,
            browser_diagnostics=self.browser_diagnostics,
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

            # Resolve model
            model_name = (
                self.browser_config.planner_model
                or self.replicant_config.llm.model
            )
            model = infer_model(model_name)

            planner_settings: dict = {"max_tokens": 1000, "reasoning_effort": "medium"}
            if self.browser_config.planner_model_settings:
                planner_settings.update(self.browser_config.planner_model_settings)

            agent: Agent[None, PlannedAction] = Agent(
                model=model,
                output_type=PlannedAction,
                instructions=system_prompt,
                model_settings=planner_settings,
            )

            if self.verbose:
                print(f"\n🤖 Planner model: {model_name}")
                print(f"   Elements: {len(self.current_observation.interactive_elements)}")
                print(f"   System prompt length: {len(system_prompt)}")

            planner_feedback: Optional[str] = None
            for _attempt in range(2):
                user_text = self._build_planner_user_message(
                    planner_feedback=planner_feedback,
                )

                if self.llm_debug:
                    sep = "=" * 80
                    print(f"\n{sep}")
                    print(f"🔬 LLM DEBUG — BROWSER PLANNER  (turn={getattr(self, '_llm_debug_turn', '?')}, attempt={_attempt + 1})")
                    print(sep)
                    print(f"Model       : {model_name}")
                    print(f"Elements    : {len(self.current_observation.interactive_elements)}")
                    print(f"URL         : {self.current_observation.url}")
                    print()
                    print("── SYSTEM PROMPT ──")
                    print(system_prompt)
                    print()
                    print("── USER MESSAGE ──")
                    print(user_text)
                    print(f"{sep}\n")

                result = await agent.run(
                    [
                        user_text,
                        BinaryContent(data=screenshot_bytes, media_type="image/png"),
                    ]
                )

                planned = result.output
                normalized_action, validation_error = self._normalize_planned_action(
                    planned
                )
                if validation_error:
                    planner_feedback = validation_error
                    if self.watch:
                        print(f"⚠️  Planner feedback: {validation_error}")
                    continue

                self._pending_planned_reasoning = planned.reasoning

                if self.watch:
                    print(f"🧠 Plan: {planned.reasoning}")
                    print(f"   → {normalized_action.action_type}", end="")
                    if normalized_action.target:
                        print(f" [element {normalized_action.target}]", end="")
                    if normalized_action.value:
                        val_preview = normalized_action.value[:60] + (
                            "…" if len(normalized_action.value) > 60 else ""
                        )
                        print(f" = \"{val_preview}\"", end="")
                    elif normalized_action.direction:
                        print(f" = \"{normalized_action.direction}\"", end="")
                    print()

                return normalized_action

            return None

        except Exception as e:
            if self.debug:
                import traceback
                traceback.print_exc()
            if self.watch:
                print(f"⚠️  Planner error: {e}")
            return None

    def _build_planner_system_prompt(self, initial_message_sent: bool) -> str:
        initial_msg_block = ""
        if not initial_message_sent and self.replicant_config.initial_message:
            initial_msg_block = (
                "\n\nWhen you reach a chat interface, your first message should be:\n"
                f'  "{self.replicant_config.initial_message}"'
            )

        return load_prompt(
            "browser_planner",
            goal=self.replicant_config.goal,
            current_date=datetime.now().strftime("%A, %B %d, %Y"),
            facts=json.dumps(self.replicant_config.facts, indent=2),
            persona_prompt=self.replicant_config.system_prompt,
            initial_message_instruction=initial_msg_block,
        )

    def _build_planner_user_message(
        self, planner_feedback: Optional[str] = None
    ) -> str:
        lines = []

        if planner_feedback:
            lines.append("Planner feedback:")
            lines.append(f"  {planner_feedback}")
            lines.append("")

        recovery_guidance = self._build_planner_recovery_guidance()
        if recovery_guidance:
            lines.append("Recovery guidance:")
            lines.extend(f"  - {hint}" for hint in recovery_guidance)
            lines.append("")

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
                    extra_hints = []
                    if elem.placeholder:
                        extra_hints.append(f'placeholder="{elem.placeholder}"')
                    if elem.current_value:
                        extra_hints.append(f'value="{elem.current_value}"')
                    if elem.is_typeahead:
                        extra_hints.append("typeahead")
                    if elem.is_expanded is True:
                        extra_hints.append("expanded")
                    hint_suffix = f" [{' | '.join(extra_hints)}]" if extra_hints else ""
                    lines.append(f"  [{elem.id}] {elem.role}{tag_hint}: {elem.name}{hint_suffix}")
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
                detail_parts = []
                if ah.get("detail"):
                    detail_parts.append(str(ah["detail"]))
                if ah.get("message"):
                    detail_parts.append(str(ah["message"]))
                detail = " -> ".join(part for part in detail_parts if part)
                lines.append(f"  {status} {ah['action']}: {detail}")
            lines.append("")

        lines.append("Decide the next action. Look at the screenshot carefully.")
        return "\n".join(lines)

    def _build_planner_recovery_guidance(self) -> List[str]:
        guidance: List[str] = []

        # Detect repetitive cycling even when actions "succeed"
        if len(self.action_history) >= 4:
            recent = self.action_history[-4:]
            action_detail_pairs = [(a["action"], a["detail"]) for a in recent]
            unique_pairs = set(action_detail_pairs)
            if len(unique_pairs) <= 2 and len(recent) >= 4:
                guidance.append(
                    "CRITICAL: You are repeating the same actions in a loop. "
                    "Stop and try a fundamentally different approach. "
                    "If a modal or panel opens, interact with the elements INSIDE it "
                    "(e.g. View Rates, select a room, fill a form) instead of immediately closing it. "
                    "If clicking a button keeps leading nowhere, try using chat or a different UI path."
                )

        recent_failures = [
            entry for entry in self.action_history[-4:]
            if not entry.get("success", True)
        ]
        if not recent_failures:
            return guidance

        failure_messages = " ".join(
            str(entry.get("message") or "").lower()
            for entry in recent_failures
        )

        if any(
            marker in failure_messages
            for marker in (
                "no longer exists in the dom",
                "stale element",
                "not attached to the dom",
                "not in the current elements list",
            )
        ):
            guidance.append(
                "The previous DOM target went stale. Treat the latest screenshot and current elements list as the source of truth, and do not retry an old element ID unless it still appears now."
            )

        if any(
            marker in failure_messages
            for marker in (
                "overlay",
                "modal",
                "drawer",
                "dialog",
                "intercepts pointer events",
                "blocking interaction",
            )
        ):
            guidance.append(
                "A visible overlay is likely blocking the background page. Focus on the modal, drawer, or dropdown that is currently open, or dismiss it with a close/cancel control or Escape."
            )

        return guidance

    # ------------------------------------------------------------------
    # Action execution
    # ------------------------------------------------------------------

    async def _execute_action_turn(
        self, action: BrowserAction, turn_index: int
    ) -> BrowserActionResult:
        before_observation = self.current_observation
        network_start = len(self.browser_diagnostics.network_events) if self.browser_diagnostics else 0
        console_start = len(self.browser_diagnostics.console_events) if self.browser_diagnostics else 0
        page_error_start = len(self.browser_diagnostics.page_errors) if self.browser_diagnostics else 0
        websocket_start = len(self.browser_diagnostics.websocket_events) if self.browser_diagnostics else 0

        if self.watch:
            if action.action_type == "send_chat":
                print(f"💬 Chat: {action.value}")
            elif action.action_type == "compose_chat":
                print(f"📝 Compose: {action.value}")
            elif action.action_type == "submit_chat":
                print(f"📤 Submit chat")
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
            planner_reasoning=self._pending_planned_reasoning,
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
                "message": self._summarize_action_message(result.message),
                "success": result.success,
                "timestamp": datetime.now(),
                "dom_changed": self._observation_changed_meaningfully(
                    before_observation,
                    result.observation,
                ),
                "had_activity": self._turn_had_activity(
                    network_start=network_start,
                    websocket_start=websocket_start,
                ),
                "activity_timestamp": self._latest_turn_activity_timestamp(
                    network_start=network_start,
                    websocket_start=websocket_start,
                ),
                "page_signature": self._observation_progress_signature(
                    result.observation,
                ),
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

        issue_screenshot = await self._capture_issue_relevant_screenshot(
            turn_index=turn_index,
            action_result=result,
            network_start=network_start,
            console_start=console_start,
            page_error_start=page_error_start,
        )
        if issue_screenshot:
            step_result.artifact_paths["issue_screenshot"] = issue_screenshot

        if self.browser_diagnostics:
            screenshot_paths = []
            for key in ("screenshot", "failure_screenshot", "issue_screenshot"):
                if key in step_result.artifact_paths:
                    screenshot_paths.append(step_result.artifact_paths[key])

            self.browser_diagnostics.turns.append(
                BrowserTurnDiagnostic(
                    turn_index=turn_index,
                    planned_reasoning=self._pending_planned_reasoning or "",
                    planned_action=action,
                    page_url_before=before_observation.url if before_observation else None,
                    page_title_before=before_observation.title if before_observation else None,
                    page_url_after=result.observation.url if result.observation else None,
                    page_title_after=result.observation.title if result.observation else None,
                    action_success=result.success,
                    action_message=result.message,
                    error=result.error,
                    screenshot_paths=screenshot_paths,
                    network_event_indexes=list(range(network_start, len(self.browser_diagnostics.network_events))),
                    console_event_indexes=list(range(console_start, len(self.browser_diagnostics.console_events))),
                    page_error_indexes=list(range(page_error_start, len(self.browser_diagnostics.page_errors))),
                    websocket_event_indexes=list(range(websocket_start, len(self.browser_diagnostics.websocket_events))),
                    observation_excerpt=self._excerpt_observation(result.observation),
                )
            )

        self._pending_planned_reasoning = None

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

        evaluator = GoalEvaluator.create(self.replicant_config, verbose=self.verbose, llm_debug=self.llm_debug)

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

    def _normalize_planned_action(
        self, planned: PlannedAction
    ) -> tuple[Optional[BrowserAction], Optional[str]]:
        action_type = planned.action_type.strip().lower()
        allowed_action_types = {
            "click",
            "compose_chat",
            "fill",
            "navigate",
            "press",
            "scroll",
            "send_chat",
            "submit_chat",
            "wait",
        }
        if action_type not in allowed_action_types:
            return None, f"Unsupported action type '{planned.action_type}'."

        target = planned.target.strip() if planned.target else None
        value = planned.value.strip() if planned.value else None
        url = planned.url.strip() if planned.url else None

        available_element_ids = {
            element.id for element in self.current_observation.interactive_elements
        } if self.current_observation else set()

        if action_type in {"click", "fill"}:
            if not target or not target.isdigit():
                return (
                    None,
                    f"{action_type} requires a numeric element ID from the current elements list.",
                )
            if available_element_ids and target not in available_element_ids:
                return (
                    None,
                    f"Element {target} is not in the current elements list.",
                )

        if action_type == "fill" and not value:
            return None, "fill requires a text value."

        if action_type == "send_chat" and not value:
            return None, "send_chat requires a message."

        if action_type == "compose_chat" and not value:
            return None, "compose_chat requires a message."

        if action_type == "press" and not value:
            return None, "press requires a key name."

        if action_type == "navigate" and not url:
            return None, "navigate requires a URL."

        if action_type == "scroll":
            direction = (value or "down").lower()
            if direction not in {"up", "down"}:
                return None, "scroll requires value 'up' or 'down'."
            return (
                BrowserAction(
                    action_type=action_type,
                    direction=direction,
                ),
                None,
            )

        return (
            BrowserAction(
                action_type=action_type,
                target=target,
                value=value,
                url=url,
            ),
            None,
        )

    def _detect_stuck_loop(self) -> bool:
        if len(self.action_history) < 3:
            return False

        consecutive_waits: List[dict] = []
        for entry in reversed(self.action_history):
            if entry.get("action") != "wait" or not entry.get("success", False):
                break
            consecutive_waits.append(entry)
        consecutive_waits.reverse()

        if len(consecutive_waits) >= self._wait_stuck_min_consecutive_waits:
            elapsed_seconds = (
                consecutive_waits[-1]["timestamp"] - consecutive_waits[0]["timestamp"]
            ).total_seconds()
            had_progress = any(
                entry.get("dom_changed") or entry.get("had_activity")
                for entry in consecutive_waits
            )
            page_signatures = {
                entry.get("page_signature", "")
                for entry in consecutive_waits
            }
            if (
                elapsed_seconds >= self._wait_stuck_threshold_seconds
                and not had_progress
                and len(page_signatures) == 1
            ):
                return True

        # Identical action repeated 3 times with no progress
        last = self.action_history[-3:]
        same_action = len({a["action"] for a in last}) == 1
        same_detail = len({a["detail"] for a in last}) == 1
        same_page = len({a.get("page_signature", "") for a in last}) == 1
        no_progress = not any(
            a.get("dom_changed") or a.get("had_activity")
            for a in last
        )
        if same_action and same_detail and same_page and no_progress:
            return True

        # Alternating-action cycle (A-B-A-B-A-B) with no net progress
        if len(self.action_history) >= 6:
            tail = self.action_history[-6:]
            action_detail_pairs = [
                (a["action"], a["detail"]) for a in tail
            ]
            even_slots = {action_detail_pairs[i] for i in range(0, 6, 2)}
            odd_slots = {action_detail_pairs[i] for i in range(1, 6, 2)}
            is_alternating = len(even_slots) == 1 and len(odd_slots) == 1 and even_slots != odd_slots
            if is_alternating and not any(
                a.get("dom_changed") or a.get("had_activity")
                for a in tail
            ):
                return True

        return False

    def _observation_changed_meaningfully(
        self,
        before: Optional[BrowserObservation],
        after: Optional[BrowserObservation],
    ) -> bool:
        if before is None or after is None:
            return before is not after

        return (
            before.url != after.url
            or before.title != after.title
            or self._normalize_visible_text(before.visible_text)
            != self._normalize_visible_text(after.visible_text)
            or self._interactive_elements_signature(before)
            != self._interactive_elements_signature(after)
        )

    def _observation_progress_signature(
        self, observation: Optional[BrowserObservation]
    ) -> str:
        if observation is None:
            return ""

        return "|".join(
            [
                observation.url,
                observation.title,
                self._normalize_visible_text(observation.visible_text),
                self._interactive_elements_signature(observation),
            ]
        )

    def _interactive_elements_signature(
        self, observation: Optional[BrowserObservation]
    ) -> str:
        if observation is None:
            return ""

        elements = [
            f"{element.role}:{element.name[:60]}:{element.tag_name}:"
            f"{(element.current_value or '')[:40]}"
            for element in observation.interactive_elements[:12]
        ]
        return "|".join(elements)

    def _normalize_visible_text(self, text: str) -> str:
        return " ".join(text.split())[:500]

    def _summarize_action_message(self, message: Optional[str]) -> str:
        if not message:
            return ""
        return " ".join(message.split())[:220]

    def _turn_had_activity(
        self,
        *,
        network_start: int,
        websocket_start: int,
    ) -> bool:
        return self._latest_turn_activity_timestamp(
            network_start=network_start,
            websocket_start=websocket_start,
        ) is not None

    def _latest_turn_activity_timestamp(
        self,
        *,
        network_start: int,
        websocket_start: int,
    ) -> Optional[datetime]:
        if not self.browser_diagnostics:
            return None

        timestamps = [
            event.timestamp
            for event in self.browser_diagnostics.network_events[network_start:]
            if event.is_first_party
        ]
        timestamps.extend(
            event.timestamp
            for event in self.browser_diagnostics.websocket_events[websocket_start:]
            if event.is_first_party
        )
        return max(timestamps) if timestamps else None

    def _action_to_message(self, action: BrowserAction) -> str:
        if action.action_type == "send_chat":
            return action.value or ""
        elif action.action_type == "compose_chat":
            return f"Compose draft: {action.value or ''}"
        elif action.action_type == "submit_chat":
            return "Submit chat"
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

    def _attach_diagnostic_listeners(self) -> None:
        page = self.browser_driver.get_page()
        if not page:
            return

        page.on("response", self._record_response)
        page.on("requestfailed", self._record_request_failed)
        page.on("console", self._record_console)
        page.on("pageerror", self._record_page_error)
        page.on("websocket", self._record_websocket)

    def _record_response(self, response: Any) -> None:
        if not self.browser_diagnostics:
            return
        try:
            self.browser_diagnostics.network_events.append(
                BrowserNetworkEvent(
                    event_type="response",
                    url=response.url,
                    method=response.request.method,
                    resource_type=response.request.resource_type,
                    status_code=response.status,
                    is_first_party=self._is_first_party_url(response.url),
                )
            )
        except Exception:
            if self.debug:
                print("⚠️  Failed to record browser response event")

    def _record_request_failed(self, request: Any) -> None:
        if not self.browser_diagnostics:
            return
        try:
            failure = request.failure
            failure_text = None
            if isinstance(failure, dict):
                failure_text = str(failure.get("errorText") or failure.get("error") or "")
            elif failure:
                failure_text = str(failure)

            self.browser_diagnostics.network_events.append(
                BrowserNetworkEvent(
                    event_type="requestfailed",
                    url=request.url,
                    method=request.method,
                    resource_type=request.resource_type,
                    failure_text=failure_text,
                    is_first_party=self._is_first_party_url(request.url),
                )
            )
        except Exception:
            if self.debug:
                print("⚠️  Failed to record browser requestfailed event")

    def _record_console(self, message: Any) -> None:
        if not self.browser_diagnostics:
            return
        try:
            location = message.location or {}
            source_url = location.get("url")
            self.browser_diagnostics.console_events.append(
                BrowserConsoleEvent(
                    level=message.type,
                    text=message.text,
                    source_url=source_url,
                    line_number=location.get("lineNumber"),
                    column_number=location.get("columnNumber"),
                    is_first_party=self._is_first_party_url(source_url),
                )
            )
        except Exception:
            if self.debug:
                print("⚠️  Failed to record browser console event")

    def _record_page_error(self, error: Any) -> None:
        if not self.browser_diagnostics:
            return
        try:
            self.browser_diagnostics.page_errors.append(
                BrowserPageErrorEvent(
                    message=str(error),
                    stack=getattr(error, "stack", None),
                )
            )
        except Exception:
            if self.debug:
                print("⚠️  Failed to record browser pageerror event")

    def _record_websocket(self, websocket: Any) -> None:
        if not self.browser_diagnostics:
            return

        try:
            url = getattr(websocket, "url", "") or ""
            is_first_party = self._is_first_party_url(url)
            self._append_websocket_event(
                url=url,
                event_type="open",
                is_first_party=is_first_party,
            )

            websocket.on(
                "framesent",
                lambda payload: self._append_websocket_event(
                    url=url,
                    event_type="framesent",
                    payload=payload,
                    is_first_party=is_first_party,
                ),
            )
            websocket.on(
                "framereceived",
                lambda payload: self._append_websocket_event(
                    url=url,
                    event_type="framereceived",
                    payload=payload,
                    is_first_party=is_first_party,
                ),
            )
            websocket.on(
                "close",
                lambda *_: self._append_websocket_event(
                    url=url,
                    event_type="close",
                    is_first_party=is_first_party,
                ),
            )
        except Exception:
            if self.debug:
                print("⚠️  Failed to record browser websocket event")

    def _append_websocket_event(
        self,
        *,
        url: str,
        event_type: str,
        is_first_party: bool,
        payload: Any = None,
    ) -> None:
        if not self.browser_diagnostics:
            return

        payload_preview, payload_size = self._summarize_websocket_payload(payload)
        self.browser_diagnostics.websocket_events.append(
            BrowserWebSocketEvent(
                event_type=event_type,
                url=url,
                payload_preview=payload_preview,
                payload_size=payload_size,
                is_first_party=is_first_party,
            )
        )

    def _summarize_websocket_payload(
        self, payload: Any
    ) -> tuple[Optional[str], Optional[int]]:
        if payload is None:
            return None, None

        if isinstance(payload, bytes):
            return payload[:120].decode("utf-8", errors="replace"), len(payload)

        payload_text = str(payload)
        return payload_text[:120], len(payload_text)

    async def _capture_issue_relevant_screenshot(
        self,
        *,
        turn_index: int,
        action_result: BrowserActionResult,
        network_start: int,
        console_start: int,
        page_error_start: int,
    ) -> Optional[str]:
        if not self.artifact_manager or not self.browser_driver:
            return None

        noteworthy_signal = (
            not action_result.success
            or self._turn_has_noteworthy_signal(
                network_start=network_start,
                console_start=console_start,
                page_error_start=page_error_start,
                observation=action_result.observation,
            )
        )
        if not noteworthy_signal:
            return None

        return await self.artifact_manager.capture_screenshot(
            self.browser_driver.get_page(),
            name=f"issue_turn_{turn_index}",
            force=True,
        )

    def _turn_has_noteworthy_signal(
        self,
        *,
        network_start: int,
        console_start: int,
        page_error_start: int,
        observation: Optional[BrowserObservation],
    ) -> bool:
        if not self.browser_diagnostics:
            return False

        for event in self.browser_diagnostics.network_events[network_start:]:
            if event.is_first_party and (
                (event.status_code is not None and event.status_code >= 400)
                or event.event_type == "requestfailed"
            ):
                return True

        for event in self.browser_diagnostics.console_events[console_start:]:
            if event.is_first_party and event.level.lower() == "error":
                return True

        if self.browser_diagnostics.page_errors[page_error_start:]:
            return True

        return self._observation_has_error_state(observation)

    def _observation_has_error_state(
        self, observation: Optional[BrowserObservation]
    ) -> bool:
        if not observation:
            return False

        visible_text = observation.visible_text.lower()
        error_markers = (
            "something went wrong",
            "unexpected error",
            "internal server error",
            "try again later",
            "unauthorized",
            "forbidden",
            "error code",
        )
        return any(marker in visible_text for marker in error_markers)

    async def _refresh_identity_context(self) -> None:
        if not self.browser_driver or not self.browser_diagnostics:
            return

        page = self.browser_driver.get_page()
        context = self.browser_driver.get_context()
        if not page or not context:
            return

        current_identity = self.browser_diagnostics.identity
        try:
            storage_result = await page.evaluate(
                """() => ({
                    userId:
                        window.localStorage.getItem('helix_authenticated_user_id') ||
                        window.localStorage.getItem('user_id') ||
                        window.localStorage.getItem('userId'),
                    conversationId:
                        window.localStorage.getItem('conversationId') ||
                        window.localStorage.getItem('conversation_id')
                })"""
            )
        except Exception:
            storage_result = {}

        user_id = self._normalize_identifier(storage_result.get("userId"))
        conversation_id = self._normalize_identifier(storage_result.get("conversationId"))

        if user_id or conversation_id:
            self.browser_diagnostics.identity = BrowserIdentityContext(
                user_id=user_id or current_identity.user_id,
                conversation_id=conversation_id or current_identity.conversation_id,
                extraction_source="local_storage",
            )
            return

        try:
            cookies = await context.cookies()
        except Exception:
            cookies = []

        cookie_map = {
            str(cookie.get("name")): self._normalize_identifier(cookie.get("value"))
            for cookie in cookies
            if cookie.get("name")
        }
        cookie_user_id = (
            cookie_map.get("helix_authenticated_user_id")
            or cookie_map.get("user_id")
            or cookie_map.get("userId")
        )
        cookie_conversation_id = (
            cookie_map.get("conversationId")
            or cookie_map.get("conversation_id")
        )
        if cookie_user_id or cookie_conversation_id:
            self.browser_diagnostics.identity = BrowserIdentityContext(
                user_id=cookie_user_id or current_identity.user_id,
                conversation_id=cookie_conversation_id or current_identity.conversation_id,
                extraction_source="cookies",
            )
            return

        auth_session_url = self._build_auth_session_url()
        if not auth_session_url:
            return

        try:
            response = await context.request.get(auth_session_url)
            if response.status != 200:
                return
            payload = await response.json()
            session_payload = payload.get("session") if isinstance(payload, dict) else {}
            session_user_id = self._normalize_identifier(
                (session_payload or {}).get("user_id")
                or (session_payload or {}).get("id")
                or (session_payload or {}).get("sub")
            )
            session_conversation_id = self._normalize_identifier(
                payload.get("conversation_id") if isinstance(payload, dict) else None
            )
            if session_user_id or session_conversation_id:
                self.browser_diagnostics.identity = BrowserIdentityContext(
                    user_id=session_user_id or current_identity.user_id,
                    conversation_id=session_conversation_id or current_identity.conversation_id,
                    extraction_source="auth_session",
                    auth_session_url=auth_session_url,
                )
        except Exception:
            return

    def _build_first_party_hosts(self) -> List[str]:
        hosts: List[str] = []
        parsed_start = urlparse(self.browser_config.start_url)
        if parsed_start.hostname:
            hosts.append(parsed_start.hostname.lower())

        for allowed in self.browser_config.domain_allowlist:
            cleaned = allowed.strip().lower()
            if cleaned:
                hosts.append(cleaned)
        return hosts

    def _is_first_party_url(self, url: Optional[str]) -> bool:
        if not url:
            return False

        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if not host:
            return False

        for candidate in self._first_party_hosts:
            if candidate.startswith("*."):
                suffix = candidate[1:]
                if host.endswith(suffix):
                    return True
            elif host == candidate or host.endswith(f".{candidate}"):
                return True
        return False

    def _build_auth_session_url(self) -> Optional[str]:
        parsed = urlparse(self.browser_config.start_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}/auth/session"

    def _normalize_identifier(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None
