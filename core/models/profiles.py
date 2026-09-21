"""Model profile definitions for Multi-Model Local V1.

Profiles map task complexity tiers to concrete Ollama model names.
The ModelRouter uses these profiles to select the right model for each task.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModelProfile(str, Enum):
    """Task-complexity tiers used by the ModelRouter."""

    FAST = "FAST"
    CODER = "CODER"
    EXPERT = "EXPERT"


@dataclass(frozen=True)
class ProfileConfig:
    """Configuration for a single model profile."""

    profile: ModelProfile
    model_name: str
    description: str
    timeout_seconds: int = 120
    temperature: float = 0.7
    max_retries: int = 2


# ---------------------------------------------------------------------------
# Default profile mapping (matches discovered Ollama models)
# ---------------------------------------------------------------------------

DEFAULT_PROFILES: dict[ModelProfile, ProfileConfig] = {
    ModelProfile.FAST: ProfileConfig(
        profile=ModelProfile.FAST,
        model_name="golden-qwen-coder-64k:latest",
        description="Fast local responses, simple questions, metadata, routing",
        timeout_seconds=60,
        temperature=0.5,
        max_retries=2,
    ),
    ModelProfile.CODER: ProfileConfig(
        profile=ModelProfile.CODER,
        model_name="golden-qwen-coder-64k:latest",
        description="Local code generation, corrections, structured JSON, MQL5",
        timeout_seconds=120,
        temperature=0.7,
        max_retries=3,
    ),
    ModelProfile.EXPERT: ProfileConfig(
        profile=ModelProfile.EXPERT,
        model_name="orcarouter/Qwen3.8-27B-Uncensored:iq4_xs",
        description="Complex reasoning, architecture, multi-file refactoring",
        timeout_seconds=300,
        temperature=0.6,
        max_retries=2,
    ),
}


def get_profile_config(profile: ModelProfile | str) -> ProfileConfig:
    """Return the ProfileConfig for the given profile, falling back to CODER."""
    if isinstance(profile, str):
        try:
            profile = ModelProfile(profile.upper())
        except ValueError:
            profile = ModelProfile.CODER
    return DEFAULT_PROFILES.get(profile, DEFAULT_PROFILES[ModelProfile.CODER])


def get_model_name_for_profile(profile: ModelProfile | str) -> str:
    """Convenience: return just the model name for a profile."""
    return get_profile_config(profile).model_name
