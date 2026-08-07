"""Role-based model catalog and runtime version fingerprint."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from app.core.config import settings


class ModelRole(StrEnum):
    PLANNER = "planner"
    REFLECTION = "reflection"
    GENERATION = "generation"
    MEMORY = "memory"
    RESEARCH = "research"
    JUDGE = "judge"


_ROLE_SETTING = {
    ModelRole.PLANNER: "model_planner",
    ModelRole.REFLECTION: "model_reflection",
    ModelRole.GENERATION: "model_generation",
    ModelRole.MEMORY: "model_memory",
    ModelRole.RESEARCH: "deep_research_model",
    ModelRole.JUDGE: "eval_judge_model",
}


def model_name(role: ModelRole) -> str:
    """Resolve the current champion for a capability role."""
    return str(getattr(settings, _ROLE_SETTING[role]))


def runtime_versions() -> dict:
    """Return versions that can change answer or safety behavior."""
    return {
        "models": {role.value: model_name(role) for role in ModelRole},
        "policy": settings.ai_policy_version,
        "prompts": settings.prompt_bundle_version,
        "evidence_schema": settings.evidence_schema_version,
        "knowledge_base": settings.knowledge_base_version,
    }


def runtime_fingerprint() -> str:
    payload = json.dumps(runtime_versions(), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
