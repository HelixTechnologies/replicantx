# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Standalone issue triage, artifact upload, and GitHub filing for browser runs.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence
from urllib.parse import quote, urlparse

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from replicantx.models import (
    BrowserConsoleEvent,
    BrowserNetworkEvent,
    BrowserPageErrorEvent,
    BrowserScenarioDiagnostics,
    BrowserTurnDiagnostic,
    IssueArtifactLink,
    IssueArtifactUploadMode,
    IssueBundle,
    IssueClassification,
    IssueDecision,
    IssueMode,
    LogfireExcerpt,
    LogfireRecord,
    ScenarioReport,
)

_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_PLAYWRIGHT_ERROR_MARKERS = (
    "element is not attached",
    "element is outside of the viewport",
    "strict mode violation",
    "waiting for selector",
    "locator.click",
    "locator.fill",
    "timeout",
    "target closed",
    "no longer exists in the dom",
)
_UI_ERROR_MARKERS = (
    "something went wrong",
    "unexpected error",
    "internal server error",
    "error code",
    "forbidden",
    "unauthorized",
    "try again later",
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "issue"


def _truncate(value: str, limit: int = 160) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _strip_query(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    path = parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _sql_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return _sql_literal(str(value))


def _render_sql_template(template: str, placeholders: dict[str, Any]) -> Optional[str]:
    rendered = template
    for name in _PLACEHOLDER_RE.findall(template):
        value = placeholders.get(name)
        if value is None or value == "":
            return None
        rendered = rendered.replace(f"{{{name}}}", _sql_value(value))
    return rendered


def _serialize_issue_bundle(bundle: IssueBundle) -> str:
    return json.dumps(bundle.model_dump(mode="json"), indent=2, ensure_ascii=False)


class LogfireTimeWindowConfig(BaseModel):
    """Relative time window around a scenario for Logfire queries."""

    model_config = ConfigDict(extra="forbid")

    before_seconds: int = Field(120, ge=0)
    after_seconds: int = Field(120, ge=0)


class LogfireCorrelationRule(BaseModel):
    """How one identity value should map into Logfire query expressions."""

    model_config = ConfigDict(extra="forbid")

    identity_field: str = Field(..., min_length=1)
    expressions: list[str] = Field(default_factory=list)
    combine_with: str = Field("or")

    @field_validator("combine_with")
    @classmethod
    def validate_combine_with(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"or", "and"}:
            raise ValueError("combine_with must be 'or' or 'and'")
        return normalized


class LogfireQueryConfig(BaseModel):
    """Configurable Logfire query definition for issue enrichment."""

    model_config = ConfigDict(extra="forbid")

    service_name: Optional[str] = Field(None)
    from_table: str = Field("records", min_length=1)
    select_fields: list[str] = Field(
        default_factory=lambda: [
            "start_timestamp",
            "level",
            "message",
            "span_name",
            "trace_id",
            "attributes",
        ]
    )
    static_filters: list[str] = Field(
        default_factory=lambda: ["service_name = {service_name}"]
    )
    correlation_rules: list[LogfireCorrelationRule] = Field(
        default_factory=lambda: [
            LogfireCorrelationRule(
                identity_field="user_id",
                expressions=["attributes->>'user_id' = {value}"],
            ),
            LogfireCorrelationRule(
                identity_field="conversation_id",
                expressions=["attributes->>'conversation_id' = {value}"],
            ),
        ]
    )
    correlation_joiner: str = Field("or")
    order_by: str = Field("start_timestamp DESC", min_length=1)
    limit: int = Field(50, ge=1)
    row_oriented: bool = Field(True)
    time_window: LogfireTimeWindowConfig = Field(
        default_factory=LogfireTimeWindowConfig
    )

    @field_validator("correlation_joiner")
    @classmethod
    def validate_correlation_joiner(cls, value: str) -> str:
        normalized = value.lower().strip()
        if normalized not in {"or", "and"}:
            raise ValueError("correlation_joiner must be 'or' or 'and'")
        return normalized

    @field_validator("from_table", "order_by")
    @classmethod
    def reject_semicolons(cls, value: str) -> str:
        if ";" in value:
            raise ValueError("SQL fragments must not contain semicolons")
        return value

    @field_validator("select_fields", "static_filters")
    @classmethod
    def reject_semicolons_in_lists(cls, values: list[str]) -> list[str]:
        for value in values:
            if ";" in value:
                raise ValueError("SQL fragments must not contain semicolons")
        return values

    @classmethod
    def default(cls, *, service_name: Optional[str]) -> "LogfireQueryConfig":
        return cls(service_name=service_name)


def _resolve_logfire_config_path(config_path: Optional[str]) -> Optional[Path]:
    if config_path:
        return Path(config_path)

    env_path = os.getenv("REPLICANTX_LOGFIRE_CONFIG")
    if env_path:
        return Path(env_path)

    for candidate in ("replicantx.logfire.yaml", "replicantx.logfire.yml"):
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _load_logfire_query_config(
    *,
    config_path: Optional[str],
    default_service_name: Optional[str],
) -> tuple[LogfireQueryConfig, Optional[Path]]:
    resolved_path = _resolve_logfire_config_path(config_path)
    if resolved_path is None:
        return (
            LogfireQueryConfig.default(service_name=default_service_name),
            None,
        )

    if not resolved_path.is_file():
        raise ValueError(f"Logfire config file not found: {resolved_path}")

    raw = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("Logfire config must contain a YAML object")

    if "logfire" in raw and isinstance(raw["logfire"], dict):
        raw = raw["logfire"]

    payload = {"service_name": default_service_name, **raw}
    return LogfireQueryConfig(**payload), resolved_path


@dataclass
class IssueProcessingConfig:
    issue_mode: IssueMode
    issue_repo: str
    artifact_upload_mode: IssueArtifactUploadMode
    issue_output_dir: Path
    artifact_bucket: str
    artifact_signed_url_ttl_seconds: int = 604800
    github_token: Optional[str] = None
    logfire_read_token: Optional[str] = None
    logfire_base_url: str = "https://logfire-api.pydantic.dev"
    logfire_service_name: str = "helix-api"
    logfire_config_path: Optional[Path] = None
    logfire_query: LogfireQueryConfig = field(
        default_factory=lambda: LogfireQueryConfig.default(service_name="helix-api")
    )
    environment: Optional[str] = None

    @classmethod
    def from_runtime(
        cls,
        *,
        issue_mode: IssueMode,
        issue_repo: str,
        artifact_upload_mode: IssueArtifactUploadMode,
        issue_output_dir: str,
        logfire_config_path: Optional[str] = None,
    ) -> "IssueProcessingConfig":
        if not _REPO_RE.match(issue_repo):
            raise ValueError("issue_repo must be in owner/name format")

        logfire_service_name = os.getenv(
            "REPLICANTX_LOGFIRE_SERVICE_NAME", "helix-api"
        )
        logfire_query, resolved_logfire_config_path = _load_logfire_query_config(
            config_path=logfire_config_path,
            default_service_name=logfire_service_name,
        )

        return cls(
            issue_mode=issue_mode,
            issue_repo=issue_repo,
            artifact_upload_mode=artifact_upload_mode,
            issue_output_dir=Path(issue_output_dir),
            artifact_bucket=os.getenv("REPLICANTX_ARTIFACT_BUCKET", "replicantx-artifacts"),
            artifact_signed_url_ttl_seconds=int(
                os.getenv("REPLICANTX_ARTIFACT_SIGNED_URL_TTL_SECONDS", "604800")
            ),
            github_token=os.getenv("REPLICANTX_GITHUB_TOKEN"),
            logfire_read_token=os.getenv("REPLICANTX_LOGFIRE_API_KEY"),
            logfire_base_url=os.getenv(
                "REPLICANTX_LOGFIRE_BASE_URL", "https://logfire-api.pydantic.dev"
            ).rstrip("/"),
            logfire_service_name=logfire_service_name,
            logfire_config_path=resolved_logfire_config_path,
            logfire_query=logfire_query,
            environment=os.getenv("REPLICANTX_ENVIRONMENT"),
        )


class IssueClassifier:
    """Deterministic classifier for browser issue candidates."""

    def classify(
        self,
        report: ScenarioReport,
        *,
        repo_target: str,
    ) -> IssueClassification:
        diagnostics = report.browser_diagnostics
        if diagnostics is None:
            return IssueClassification(
                decision=IssueDecision.SKIP,
                confidence=0.0,
                subtypes=["non-browser-scenario"],
                fingerprint=self._fingerprint(
                    repo_target=repo_target,
                    scenario_name=report.scenario_name,
                    signature="non-browser-scenario",
                ),
                summary="Scenario did not produce browser diagnostics.",
                reasons=["Only browser scenarios are eligible for issue triage."],
                relevant_turn_indexes=[],
            )

        subtypes: set[str] = set()
        reasons: list[str] = []
        relevant_turns: set[int] = set()
        confidence = 0.2
        signature = report.error or report.justification or report.scenario_name
        decision = IssueDecision.SKIP

        for index, event in enumerate(diagnostics.network_events):
            if not event.is_first_party:
                continue
            turns = self._turns_for_event(diagnostics.turns, "network", index)

            if event.status_code is not None and event.status_code >= 500:
                decision = IssueDecision.AUTO_FILE
                confidence = max(confidence, 0.98)
                subtype = "network-5xx"
                subtypes.add(subtype)
                signature = f"{subtype}:{_strip_query(event.url)}"
                relevant_turns.update(turns)
                reasons.append(
                    f"First-party {event.status_code} response detected at {_strip_query(event.url)}."
                )
            elif event.status_code in (401, 403):
                subtype = f"network-{event.status_code}"
                subtypes.add(subtype)
                relevant_turns.update(turns)
                signature = f"{subtype}:{_strip_query(event.url)}"
                if diagnostics.identity.user_id:
                    decision = IssueDecision.AUTO_FILE
                    confidence = max(confidence, 0.94)
                    reasons.append(
                        f"First-party {event.status_code} response happened after authenticated identity was detected."
                    )
                else:
                    decision = self._upgrade_decision(decision, IssueDecision.REVIEW)
                    confidence = max(confidence, 0.6)
                    reasons.append(
                        f"First-party {event.status_code} response occurred before authenticated identity could be confirmed."
                    )
            elif event.event_type == "requestfailed":
                decision = self._upgrade_decision(decision, IssueDecision.REVIEW)
                confidence = max(confidence, 0.55)
                subtypes.add("network-requestfailed")
                relevant_turns.update(turns)
                signature = f"requestfailed:{_strip_query(event.url)}:{event.failure_text or 'unknown'}"
                reasons.append(
                    f"First-party request failed for {_strip_query(event.url)}."
                )

        for index, console_event in enumerate(diagnostics.console_events):
            if console_event.is_first_party and console_event.level.lower() == "error":
                decision = IssueDecision.AUTO_FILE
                confidence = max(confidence, 0.92)
                subtypes.add("console-error")
                relevant_turns.update(self._turns_for_event(diagnostics.turns, "console", index))
                signature = f"console-error:{console_event.text}"
                reasons.append("First-party browser console error was recorded.")

        for index, page_error in enumerate(diagnostics.page_errors):
            if page_error.is_first_party:
                decision = IssueDecision.AUTO_FILE
                confidence = max(confidence, 0.95)
                subtypes.add("pageerror")
                relevant_turns.update(self._turns_for_event(diagnostics.turns, "page_error", index))
                signature = f"pageerror:{page_error.message}"
                reasons.append("Unhandled browser page error was recorded.")

        ui_error_turns = self._ui_error_turns(diagnostics.turns)
        if ui_error_turns:
            relevant_turns.update(ui_error_turns)
            subtypes.add("ui-explicit-error")
            if decision == IssueDecision.AUTO_FILE:
                confidence = max(confidence, 0.9)
                reasons.append("The page showed an explicit error state corroborated by other first-party signals.")
            else:
                decision = self._upgrade_decision(decision, IssueDecision.REVIEW)
                confidence = max(confidence, 0.62)
                reasons.append("The page showed an explicit error state without strong corroborating signals.")

        if report.error and "stuck loop" in report.error.lower():
            decision = self._upgrade_decision(decision, IssueDecision.REVIEW)
            confidence = max(confidence, 0.58)
            subtypes.add("stuck-loop")
            reasons.append("Scenario ended in a stuck loop and requires manual review.")

        failed_turns = [turn for turn in diagnostics.turns if not turn.action_success]
        if failed_turns and decision != IssueDecision.AUTO_FILE:
            relevant_turns.update(turn.turn_index for turn in failed_turns)
            failed_error_text = " ".join(turn.error or turn.action_message for turn in failed_turns)
            if any(marker in failed_error_text.lower() for marker in _PLAYWRIGHT_ERROR_MARKERS):
                decision = IssueDecision.SKIP
                confidence = max(confidence, 0.88)
                subtypes.add("playwright-gap")
                signature = failed_error_text
                reasons.append(
                    "Failures match Playwright/control limitations without corroborating first-party app signals."
                )
            else:
                decision = self._upgrade_decision(decision, IssueDecision.REVIEW)
                confidence = max(confidence, 0.56)
                subtypes.add("ambiguous-ui")
                signature = failed_error_text
                reasons.append("Action failures could be app or automation related.")

        if report.passed and decision == IssueDecision.SKIP and not subtypes:
            subtypes.add("no-issue-signal")
            reasons.append("Scenario passed and no first-party error signals were detected.")
            signature = "no-issue-signal"

        if report.passed and decision != IssueDecision.SKIP:
            reasons.append(
                "Scenario still achieved its goal; the issue was observed during a progressing user flow."
            )

        if not relevant_turns and diagnostics.turns:
            relevant_turns.add(diagnostics.turns[-1].turn_index)

        if not subtypes:
            subtypes.add("uncategorized")

        fingerprint = self._fingerprint(
            repo_target=repo_target,
            scenario_name=report.scenario_name,
            signature=signature,
        )

        return IssueClassification(
            decision=decision,
            confidence=round(confidence, 2),
            subtypes=sorted(subtypes),
            fingerprint=fingerprint,
            summary=self._build_summary(report, decision, sorted(subtypes)),
            reasons=reasons or ["No issue-worthy browser signal detected."],
            relevant_turn_indexes=sorted(relevant_turns),
        )

    def _upgrade_decision(
        self, current: IssueDecision, new: IssueDecision
    ) -> IssueDecision:
        order = {
            IssueDecision.SKIP: 0,
            IssueDecision.REVIEW: 1,
            IssueDecision.AUTO_FILE: 2,
        }
        return new if order[new] > order[current] else current

    def _turns_for_event(
        self,
        turns: Sequence[BrowserTurnDiagnostic],
        event_kind: str,
        event_index: int,
    ) -> set[int]:
        matched: set[int] = set()
        for turn in turns:
            indexes = {
                "network": turn.network_event_indexes,
                "console": turn.console_event_indexes,
                "page_error": turn.page_error_indexes,
            }[event_kind]
            if event_index in indexes:
                matched.add(turn.turn_index)
        return matched

    def _ui_error_turns(self, turns: Sequence[BrowserTurnDiagnostic]) -> set[int]:
        matched: set[int] = set()
        for turn in turns:
            text = turn.observation_excerpt.lower()
            if any(marker in text for marker in _UI_ERROR_MARKERS):
                matched.add(turn.turn_index)
        return matched

    def _build_summary(
        self,
        report: ScenarioReport,
        decision: IssueDecision,
        subtypes: Sequence[str],
    ) -> str:
        primary = subtypes[0] if subtypes else "uncategorized"
        outcome_suffix = " Goal was still achieved." if report.passed and decision != IssueDecision.SKIP else ""
        return (
            f"{decision.value.replace('_', ' ').title()} for scenario "
            f"'{report.scenario_name}' ({primary}).{outcome_suffix}"
        )

    def _fingerprint(self, *, repo_target: str, scenario_name: str, signature: str) -> str:
        payload = f"{repo_target}|{scenario_name}|{_truncate(signature, 300)}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:20]


class SupabaseArtifactUploader:
    """Uploads issue artifacts to private Supabase Storage and returns signed URLs."""

    def __init__(
        self,
        *,
        supabase_url: Optional[str],
        service_role_key: Optional[str],
        bucket: str,
        signed_url_ttl_seconds: int,
    ):
        self.supabase_url = (supabase_url or "").rstrip("/")
        self.service_role_key = service_role_key or ""
        self.bucket = bucket
        self.signed_url_ttl_seconds = signed_url_ttl_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.supabase_url and self.service_role_key and self.bucket)

    async def upload_artifacts(
        self,
        *,
        report: ScenarioReport,
        classification: IssueClassification,
        local_artifacts: Sequence[IssueArtifactLink],
        allowed_roots: Sequence[Path],
    ) -> list[IssueArtifactLink]:
        if not self.is_configured:
            return list(local_artifacts)

        uploaded: list[IssueArtifactLink] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for artifact in local_artifacts:
                local_path = Path(artifact.local_path).resolve()
                self._ensure_allowed_path(local_path, allowed_roots)
                if not local_path.is_file():
                    uploaded.append(artifact)
                    continue

                content_type = mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
                storage_path = (
                    f"browser-issues/{datetime.now(timezone.utc).strftime('%Y/%m/%d')}/"
                    f"{classification.fingerprint}/{_slugify(local_path.name)}"
                )
                await self._upload_file(
                    client=client,
                    storage_path=storage_path,
                    content_type=content_type,
                    content=local_path.read_bytes(),
                )
                signed_url = await self._create_signed_url(
                    client=client,
                    storage_path=storage_path,
                )
                uploaded.append(
                    IssueArtifactLink(
                        kind=artifact.kind,
                        label=artifact.label,
                        local_path=artifact.local_path,
                        uploaded_url=signed_url,
                    )
                )
        return uploaded

    async def _upload_file(
        self,
        *,
        client: httpx.AsyncClient,
        storage_path: str,
        content_type: str,
        content: bytes,
    ) -> None:
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket}/{storage_path}"
        response = await client.post(
            url,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            content=content,
        )
        response.raise_for_status()

    async def _create_signed_url(
        self,
        *,
        client: httpx.AsyncClient,
        storage_path: str,
    ) -> Optional[str]:
        url = f"{self.supabase_url}/storage/v1/object/sign/{self.bucket}/{storage_path}"
        response = await client.post(
            url,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": "application/json",
            },
            json={"expiresIn": self.signed_url_ttl_seconds},
        )
        response.raise_for_status()
        payload = response.json()
        signed_path = payload.get("signedURL") or payload.get("signedUrl")
        if not signed_path:
            return None
        if str(signed_path).startswith("http"):
            return str(signed_path)
        return f"{self.supabase_url}/storage/v1{signed_path}"

    def _ensure_allowed_path(self, path: Path, allowed_roots: Sequence[Path]) -> None:
        resolved_allowed = [root.resolve() for root in allowed_roots if root.exists()]
        if not any(root == path or root in path.parents for root in resolved_allowed):
            raise ValueError(f"Refusing to upload artifact outside allowed roots: {path}")


class HttpLogfireClient:
    """Retrieves compact Logfire excerpts over the Logfire query API."""

    def __init__(
        self,
        *,
        read_token: Optional[str],
        base_url: str,
        query_config: LogfireQueryConfig,
    ):
        self.read_token = read_token or ""
        self.base_url = base_url.rstrip("/")
        self.query_config = query_config

    @property
    def is_configured(self) -> bool:
        return bool(self.read_token and self.base_url)

    async def fetch_excerpt(
        self,
        diagnostics: BrowserScenarioDiagnostics,
    ) -> LogfireExcerpt:
        if not self.is_configured:
            return LogfireExcerpt(
                query_window_start=None,
                query_window_end=None,
                query_sql=None,
                fetched=False,
                unavailable_reason="Logfire token or base URL not configured.",
            )

        sql = self._build_sql(diagnostics)
        if sql is None:
            return LogfireExcerpt(
                query_window_start=None,
                query_window_end=None,
                query_sql=None,
                fetched=False,
                unavailable_reason="No configured Logfire correlation values were available for this run.",
            )
        started_at = diagnostics.started_at.astimezone(timezone.utc) - timedelta(
            seconds=self.query_config.time_window.before_seconds
        )
        completed_at = (
            (diagnostics.completed_at or diagnostics.started_at).astimezone(timezone.utc)
            + timedelta(seconds=self.query_config.time_window.after_seconds)
        )

        params = {
            "sql": sql,
            "limit": str(self.query_config.limit),
            "row_oriented": str(self.query_config.row_oriented).lower(),
            "min_timestamp": started_at.isoformat(),
            "max_timestamp": completed_at.isoformat(),
        }
        headers = {
            "Authorization": f"Bearer {self.read_token}",
            "Accept": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/query",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            return LogfireExcerpt(
                query_window_start=started_at.isoformat(),
                query_window_end=completed_at.isoformat(),
                query_sql=sql,
                fetched=False,
                unavailable_reason=f"Logfire query failed: {exc.__class__.__name__}",
            )

        records_payload: Iterable[dict[str, Any]]
        if isinstance(payload, list):
            records_payload = payload
        elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
            records_payload = payload["rows"]
        else:
            records_payload = []

        records: list[LogfireRecord] = []
        for row in records_payload:
            attributes = row.get("attributes") or {}
            if isinstance(attributes, str):
                try:
                    attributes = json.loads(attributes)
                except Exception:
                    attributes = {"raw": attributes}
            records.append(
                LogfireRecord(
                    timestamp=str(row.get("start_timestamp") or row.get("timestamp") or ""),
                    level=row.get("level"),
                    message=row.get("message"),
                    span_name=row.get("span_name"),
                    trace_id=row.get("trace_id"),
                    attributes=attributes if isinstance(attributes, dict) else {"raw": attributes},
                )
            )

        return LogfireExcerpt(
            query_window_start=started_at.isoformat(),
            query_window_end=completed_at.isoformat(),
            query_sql=sql,
            fetched=True,
            unavailable_reason=None,
            records=records,
        )

    def _build_sql(self, diagnostics: BrowserScenarioDiagnostics) -> Optional[str]:
        placeholders = {
            "service_name": self.query_config.service_name,
            "environment": diagnostics.environment,
            "scenario_name": diagnostics.scenario_name,
            "goal": diagnostics.goal,
            "user_id": diagnostics.identity.user_id,
            "conversation_id": diagnostics.identity.conversation_id,
        }

        where_clauses: list[str] = []
        for filter_template in self.query_config.static_filters:
            rendered_filter = _render_sql_template(filter_template, placeholders)
            if rendered_filter:
                where_clauses.append(rendered_filter)

        correlation_clauses: list[str] = []
        for rule in self.query_config.correlation_rules:
            identity_value = getattr(diagnostics.identity, rule.identity_field, None)
            if identity_value is None or identity_value == "":
                continue

            rule_placeholders = {**placeholders, "value": identity_value}
            rendered_expressions = [
                rendered
                for rendered in (
                    _render_sql_template(expression, rule_placeholders)
                    for expression in rule.expressions
                )
                if rendered
            ]
            if not rendered_expressions:
                continue

            if len(rendered_expressions) == 1:
                correlation_clauses.append(rendered_expressions[0])
            else:
                joiner = f" {rule.combine_with.upper()} "
                correlation_clauses.append(
                    f"({joiner.join(rendered_expressions)})"
                )

        if not correlation_clauses:
            return None

        if len(correlation_clauses) == 1:
            where_clauses.append(correlation_clauses[0])
        else:
            joiner = f" {self.query_config.correlation_joiner.upper()} "
            where_clauses.append(f"({joiner.join(correlation_clauses)})")

        sql = (
            f"SELECT {', '.join(self.query_config.select_fields)} "
            f"FROM {self.query_config.from_table}"
        )
        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)
        sql += f" ORDER BY {self.query_config.order_by}"
        return sql


class GitHubIssueTracker:
    """Creates and deduplicates GitHub issues using the REST API."""

    def __init__(self, *, token: Optional[str], api_base_url: str = "https://api.github.com"):
        self.token = token or ""
        self.api_base_url = api_base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.token)

    async def create_or_comment(
        self,
        *,
        repo: str,
        title: str,
        body: str,
        fingerprint: str,
        labels: Sequence[str],
    ) -> Optional[str]:
        if not self.is_configured:
            return None

        owner, name = repo.split("/", 1)
        async with httpx.AsyncClient(timeout=30.0) as client:
            existing = await self._find_existing_issue(
                client=client,
                repo=repo,
                fingerprint=fingerprint,
            )
            if existing:
                await self._create_comment(
                    client=client,
                    owner=owner,
                    repo=name,
                    issue_number=existing["number"],
                    body=f"### ReplicantX reproduction\n\n{body}",
                )
                return str(existing.get("html_url"))

            await self._ensure_labels(client=client, owner=owner, repo=name, labels=labels)
            response = await client.post(
                f"{self.api_base_url}/repos/{owner}/{name}/issues",
                headers=self._headers(),
                json={
                    "title": title,
                    "body": body,
                    "labels": list(labels),
                },
            )
            response.raise_for_status()
            payload = response.json()
            return str(payload.get("html_url"))

    async def _find_existing_issue(
        self,
        *,
        client: httpx.AsyncClient,
        repo: str,
        fingerprint: str,
    ) -> Optional[dict[str, Any]]:
        response = await client.get(
            f"{self.api_base_url}/search/issues",
            headers=self._headers(),
            params={
                "q": f'repo:{repo} is:issue is:open "{fingerprint}" in:body',
                "per_page": "1",
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("items") or []
        return items[0] if items else None

    async def _create_comment(
        self,
        *,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        issue_number: int,
        body: str,
    ) -> None:
        response = await client.post(
            f"{self.api_base_url}/repos/{owner}/{repo}/issues/{issue_number}/comments",
            headers=self._headers(),
            json={"body": body},
        )
        response.raise_for_status()

    async def _ensure_labels(
        self,
        *,
        client: httpx.AsyncClient,
        owner: str,
        repo: str,
        labels: Sequence[str],
    ) -> None:
        for label in labels:
            payload = {
                "name": label,
                "color": self._label_color(label),
                "description": "Auto-created by ReplicantX issue reporting",
            }
            response = await client.post(
                f"{self.api_base_url}/repos/{owner}/{repo}/labels",
                headers=self._headers(),
                json=payload,
            )
            if response.status_code not in (201, 422):
                response.raise_for_status()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _label_color(self, label: str) -> str:
        palette = {
            "bug": "d73a4a",
            "source:replicantx": "5319e7",
            "triage:auto-file": "b60205",
            "triage:review": "fbca04",
            "subtype:network-5xx": "cb2431",
            "subtype:network-401": "d93f0b",
            "subtype:network-403": "d93f0b",
            "subtype:console-error": "c2e0c6",
            "subtype:pageerror": "c2e0c6",
            "subtype:playwright-gap": "bfdadc",
            "subtype:ambiguous-ui": "f9d0c4",
            "subtype:ui-explicit-error": "e99695",
        }
        return palette.get(label, "ededed")


class IssueProcessor:
    """Orchestrates bundle creation, enrichment, and optional issue filing."""

    def __init__(
        self,
        *,
        config: IssueProcessingConfig,
        classifier: Optional[IssueClassifier] = None,
        uploader: Optional[SupabaseArtifactUploader] = None,
        logfire_client: Optional[HttpLogfireClient] = None,
        issue_tracker: Optional[GitHubIssueTracker] = None,
    ):
        self.config = config
        self.classifier = classifier or IssueClassifier()
        self.uploader = uploader or SupabaseArtifactUploader(
            supabase_url=os.getenv("SUPABASE_URL"),
            service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            bucket=config.artifact_bucket,
            signed_url_ttl_seconds=config.artifact_signed_url_ttl_seconds,
        )
        self.logfire_client = logfire_client or HttpLogfireClient(
            read_token=config.logfire_read_token,
            base_url=config.logfire_base_url,
            query_config=config.logfire_query,
        )
        self.issue_tracker = issue_tracker or GitHubIssueTracker(
            token=config.github_token,
        )

    async def process_suite(self, scenario_reports: Sequence[ScenarioReport]) -> None:
        self.config.issue_output_dir.mkdir(parents=True, exist_ok=True)

        for report in scenario_reports:
            if report.browser_diagnostics is None:
                continue
            if not self._should_process(report):
                continue

            classification = self.classifier.classify(
                report,
                repo_target=self.config.issue_repo,
            )
            report.issue_classification = classification

            output_dir = self.config.issue_output_dir / _slugify(report.scenario_name)
            output_dir.mkdir(parents=True, exist_ok=True)

            logfire_excerpt = await self.logfire_client.fetch_excerpt(report.browser_diagnostics)
            artifact_links = self._collect_local_artifacts(report, classification)

            if (
                classification.decision == IssueDecision.AUTO_FILE
                and self.config.artifact_upload_mode == IssueArtifactUploadMode.ON
            ):
                try:
                    artifact_links = await self.uploader.upload_artifacts(
                        report=report,
                        classification=classification,
                        local_artifacts=artifact_links,
                        allowed_roots=self._allowed_roots(report, output_dir),
                    )
                except Exception:
                    # Degrade gracefully: keep local paths if upload fails.
                    artifact_links = list(artifact_links)

            issue_title = self._render_issue_title(report, classification)
            issue_body = self._render_issue_body(
                report=report,
                classification=classification,
                artifact_links=artifact_links,
                logfire_excerpt=logfire_excerpt,
            )

            bundle = IssueBundle(
                scenario_name=report.scenario_name,
                scenario_file=report.source_file,
                repo_target=self.config.issue_repo,
                goal=report.browser_diagnostics.goal,
                environment=self.config.environment or report.browser_diagnostics.environment,
                scenario_passed=report.passed,
                scenario_error=report.error,
                classification=classification,
                diagnostics=report.browser_diagnostics,
                artifact_links=artifact_links,
                logfire_excerpt=logfire_excerpt,
                issue_title=issue_title,
                issue_body=issue_body,
            )

            markdown_path = output_dir / "issue.md"
            bundle_path = output_dir / "issue_bundle.json"
            markdown_path.write_text(issue_body, encoding="utf-8")
            bundle_path.write_text(_serialize_issue_bundle(bundle), encoding="utf-8")

            report.issue_markdown_path = str(markdown_path)
            report.issue_bundle_path = str(bundle_path)

            if (
                classification.decision == IssueDecision.AUTO_FILE
                and self.config.issue_mode == IssueMode.AUTO_HIGH_CONFIDENCE
            ):
                labels = self._labels_for_classification(classification)
                try:
                    issue_url = await self.issue_tracker.create_or_comment(
                        repo=self.config.issue_repo,
                        title=issue_title,
                        body=issue_body,
                        fingerprint=classification.fingerprint,
                        labels=labels,
                    )
                    report.issue_url = issue_url
                except Exception:
                    report.issue_url = None

    def _should_process(self, report: ScenarioReport) -> bool:
        diagnostics = report.browser_diagnostics
        if diagnostics is None:
            return False
        if not report.passed:
            return True
        return any(
            event.is_first_party and (
                (event.status_code is not None and event.status_code >= 400)
                or event.event_type == "requestfailed"
            )
            for event in diagnostics.network_events
        ) or any(
            event.is_first_party and event.level.lower() == "error"
            for event in diagnostics.console_events
        ) or any(event.is_first_party for event in diagnostics.page_errors)

    def _allowed_roots(self, report: ScenarioReport, output_dir: Path) -> list[Path]:
        roots = [output_dir]
        diagnostics = report.browser_diagnostics
        if diagnostics and diagnostics.artifact_dir:
            roots.append(Path(diagnostics.artifact_dir))
        return roots

    def _collect_local_artifacts(
        self,
        report: ScenarioReport,
        classification: IssueClassification,
    ) -> list[IssueArtifactLink]:
        diagnostics = report.browser_diagnostics
        if diagnostics is None:
            return []

        links: list[IssueArtifactLink] = []
        seen: set[str] = set()
        relevant_turns = set(classification.relevant_turn_indexes)
        for turn in diagnostics.turns:
            if turn.turn_index not in relevant_turns:
                continue
            for screenshot in turn.screenshot_paths:
                if screenshot in seen:
                    continue
                seen.add(screenshot)
                links.append(
                    IssueArtifactLink(
                        kind="screenshot",
                        label=f"Turn {turn.turn_index} screenshot",
                        local_path=screenshot,
                        uploaded_url=None,
                    )
                )

        if diagnostics.trace_path and diagnostics.trace_path not in seen:
            seen.add(diagnostics.trace_path)
            links.append(
                IssueArtifactLink(
                    kind="trace",
                    label="Playwright trace",
                    local_path=diagnostics.trace_path,
                    uploaded_url=None,
                )
            )

        return links

    def _render_issue_title(
        self,
        report: ScenarioReport,
        classification: IssueClassification,
    ) -> str:
        primary = classification.subtypes[0] if classification.subtypes else "uncategorized"
        diagnostics = report.browser_diagnostics
        env = self.config.environment or (diagnostics.environment if diagnostics else None) or "unknown"
        return f"[ReplicantX][{primary}][{env}] {report.scenario_name}"

    def _render_issue_body(
        self,
        *,
        report: ScenarioReport,
        classification: IssueClassification,
        artifact_links: Sequence[IssueArtifactLink],
        logfire_excerpt: LogfireExcerpt,
    ) -> str:
        diagnostics = report.browser_diagnostics
        assert diagnostics is not None

        lines = [
            f"<!-- replicantx-fingerprint: {classification.fingerprint} -->",
            "## Summary",
            classification.summary,
            "",
            "## Context",
            f"- Scenario: `{report.scenario_name}`",
            f"- Scenario file: `{report.source_file or 'unknown'}`",
            f"- Goal: `{diagnostics.goal}`",
            f"- Environment: `{self.config.environment or diagnostics.environment or 'unknown'}`",
            f"- Scenario outcome: `{'passed' if report.passed else 'failed'}`",
            f"- Decision: `{classification.decision.value}`",
            f"- Confidence: `{classification.confidence:.2f}`",
            f"- Subtypes: `{', '.join(classification.subtypes)}`",
            f"- User ID: `{diagnostics.identity.user_id or 'unavailable'}`",
            f"- Conversation ID: `{diagnostics.identity.conversation_id or 'unavailable'}`",
            f"- Started: `{diagnostics.started_at.isoformat()}`",
            f"- Completed: `{(diagnostics.completed_at or diagnostics.started_at).isoformat()}`",
            "",
            "## Why This Was Classified",
        ]
        for reason in classification.reasons:
            lines.append(f"- {reason}")

        lines.extend(["", "## Replicant Trace"])
        for turn in diagnostics.turns:
            if turn.turn_index not in classification.relevant_turn_indexes:
                continue
            action_summary = turn.action_message or (
                turn.planned_action.action_type if turn.planned_action else "unknown"
            )
            lines.extend(
                [
                    f"### Turn {turn.turn_index}",
                    f"- Reasoning: {_truncate(turn.planned_reasoning or 'No reasoning captured', 500)}",
                    f"- Action: `{action_summary}`",
                    f"- Success: `{turn.action_success}`",
                    f"- Error: `{turn.error or 'none'}`",
                    f"- Observation: `{_truncate(turn.observation_excerpt, 400)}`",
                ]
            )

        lines.extend(["", "## Browser Signals"])
        signal_lines = self._render_signal_lines(diagnostics, classification.relevant_turn_indexes)
        if signal_lines:
            lines.extend(signal_lines)
        else:
            lines.append("- No first-party browser signals captured.")

        lines.extend(["", "## Artifacts"])
        if artifact_links:
            for artifact in artifact_links:
                target = artifact.uploaded_url or artifact.local_path
                lines.append(f"- {artifact.label}: {target}")
        else:
            lines.append("- No relevant artifacts were captured.")

        lines.extend(["", "## Logfire"])
        if logfire_excerpt.fetched and logfire_excerpt.records:
            lines.append("```text")
            for record in logfire_excerpt.records[:12]:
                lines.append(
                    f"{record.timestamp} | {record.level or '-'} | {record.span_name or '-'} | "
                    f"{_truncate(record.message or '', 180)}"
                )
            lines.append("```")
        else:
            lines.append(
                f"Logs unavailable: {logfire_excerpt.unavailable_reason or 'No matching records found.'}"
            )

        return "\n".join(lines) + "\n"

    def _render_signal_lines(
        self,
        diagnostics: BrowserScenarioDiagnostics,
        relevant_turn_indexes: Sequence[int],
    ) -> list[str]:
        lines: list[str] = []
        relevant = set(relevant_turn_indexes)

        for turn in diagnostics.turns:
            if turn.turn_index not in relevant:
                continue
            for index in turn.network_event_indexes:
                network_event = diagnostics.network_events[index]
                if not network_event.is_first_party:
                    continue
                if network_event.status_code is not None:
                    lines.append(
                        f"- Network: `{network_event.method} {_strip_query(network_event.url)} -> {network_event.status_code}`"
                    )
                elif network_event.failure_text:
                    lines.append(
                        f"- Network: `{network_event.method} {_strip_query(network_event.url)} failed: {_truncate(network_event.failure_text, 120)}`"
                    )
            for index in turn.console_event_indexes:
                console_event = diagnostics.console_events[index]
                if console_event.is_first_party:
                    lines.append(
                        f"- Console `{console_event.level}`: `{_truncate(console_event.text, 180)}`"
                    )
            for index in turn.page_error_indexes:
                page_error = diagnostics.page_errors[index]
                if page_error.is_first_party:
                    lines.append(f"- Page error: `{_truncate(page_error.message, 180)}`")
        return lines[:20]

    def _labels_for_classification(self, classification: IssueClassification) -> list[str]:
        labels = ["bug", "source:replicantx"]
        if classification.decision == IssueDecision.AUTO_FILE:
            labels.append("triage:auto-file")
        elif classification.decision == IssueDecision.REVIEW:
            labels.append("triage:review")

        for subtype in classification.subtypes:
            labels.append(f"subtype:{subtype}")
        return labels
