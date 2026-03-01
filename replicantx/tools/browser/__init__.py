# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Browser automation toolkit for ReplicantX browser mode.
"""

from .observation import (
    extract_observation,
    detect_chat_input,
    detect_chat_send_button,
)
from .actions import execute_action
from .artifacts import ArtifactManager
from .playwright_manager import BrowserAutomationDriver

__all__ = [
    "extract_observation",
    "detect_chat_input",
    "detect_chat_send_button",
    "execute_action",
    "ArtifactManager",
    "BrowserAutomationDriver",
]
