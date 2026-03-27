# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""Prompt template loading utilities."""

from pathlib import Path
from string import Template
from typing import Dict

import yaml

_PROMPTS_DIR = Path(__file__).parent
_cache: Dict[str, str] = {}


def load_prompt(name: str, **variables: str) -> str:
    """Load a prompt template from a YAML file and render it.

    Templates use Python ``string.Template`` syntax (``$variable`` or
    ``${variable}``).  Unknown placeholders are left as-is so that
    partially-rendered templates don't raise.

    Args:
        name: Filename (without ``.yaml`` extension) in the prompts directory.
        **variables: Values to substitute into the template.

    Returns:
        The rendered prompt string.
    """
    if name not in _cache:
        path = _PROMPTS_DIR / f"{name}.yaml"
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        _cache[name] = data["template"]

    return Template(_cache[name]).safe_substitute(variables)
