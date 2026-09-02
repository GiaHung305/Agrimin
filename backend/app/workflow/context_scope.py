"""Minimize owned user context before it enters model prompts."""

from __future__ import annotations

from typing import Any


_PROFILE_PROMPT_FIELDS = (
    "province",
    "area_ha",
    "farming_style",
)
_SEASON_PROMPT_FIELDS = (
    "plot_name",
    "plot_area_ha",
    "crop",
    "variety",
    "growth_stage",
    "planted_on",
    "expected_harvest_on",
    "status",
    "recorded_status",
    "data_warning",
)


def _present_fields(record: dict[str, Any], allowed: tuple[str, ...]) -> dict:
    return {
        field: record[field]
        for field in allowed
        if record.get(field) not in (None, "")
    }


def scoped_owned_context(context: dict, *, include: bool) -> dict:
    """Return only model-useful owned data, never internal identifiers.

    The complete records remain in graph state for deterministic application
    logic. This projection is exclusively for prompts sent to model providers.
    """
    if not include:
        return {
            "farm_profile": {},
            "plot_seasons": [],
            "known_facts": [],
        }

    profile = context.get("farm_profile")
    seasons = context.get("plot_seasons") or []
    return {
        "farm_profile": (
            _present_fields(profile, _PROFILE_PROMPT_FIELDS)
            if isinstance(profile, dict)
            else {}
        ),
        "plot_seasons": [
            projected
            for season in seasons
            if isinstance(season, dict)
            and (projected := _present_fields(season, _SEASON_PROMPT_FIELDS))
        ],
        "known_facts": [
            fact
            for fact in (context.get("known_facts") or [])
            if isinstance(fact, dict)
        ],
    }
