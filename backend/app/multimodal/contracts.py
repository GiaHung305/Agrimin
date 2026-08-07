"""Typed visual observations kept strictly separate from diagnosis."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "visual-observation-v1"
_DIAGNOSIS_PATTERN = re.compile(
    r"\b(bệnh|chẩn đoán|nhiễm|do nấm|do vi khuẩn|virus|phytophthora|fusarium)\b",
    re.IGNORECASE,
)


class NormalizedRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x_min: float = Field(ge=0.0, le=1.0)
    y_min: float = Field(ge=0.0, le=1.0)
    x_max: float = Field(ge=0.0, le=1.0)
    y_max: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_extents(self):
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("region max coordinates must exceed min coordinates")
        return self


class VisibleSymptom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symptom_type: Literal[
        "discoloration",
        "spot",
        "lesion",
        "wilting",
        "curling",
        "hole",
        "mold_like_growth",
        "rot_like_tissue",
        "cracking",
        "other",
    ]
    description: str = Field(min_length=2, max_length=300)
    colors: list[
        Literal[
            "green",
            "yellow",
            "brown",
            "black",
            "white",
            "gray",
            "red",
            "purple",
            "orange",
            "unknown",
        ]
    ] = Field(default_factory=list, max_length=3)
    distribution: Literal[
        "localized",
        "scattered",
        "edge",
        "interveinal",
        "whole_part",
        "unknown",
    ] = "unknown"
    region: NormalizedRegion | None = None
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def forbid_diagnosis_language(self):
        if _DIAGNOSIS_PATTERN.search(self.description):
            raise ValueError("symptom description must be visual, not diagnostic")
        return self


class VisualObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(pattern=r"^[0-9a-f]{16}$")
    relevance: Literal[
        "agriculture_plant",
        "agriculture_non_plant",
        "out_of_domain",
        "uncertain",
    ]
    crop_candidate: str | None = Field(default=None, max_length=100)
    plant_part: Literal[
        "leaf",
        "stem",
        "fruit",
        "flower",
        "root",
        "whole_plant",
        "multiple",
        "unknown",
    ] = "unknown"
    visible_symptoms: list[VisibleSymptom] = Field(default_factory=list, max_length=8)
    limitations: list[
        Literal[
            "low_light",
            "overexposed",
            "blur",
            "occlusion",
            "too_far",
            "single_view",
            "background_clutter",
            "unknown_crop",
            "none",
        ]
    ] = Field(default_factory=list, max_length=6)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_relevance_scope(self):
        if self.relevance == "out_of_domain" and (
            self.crop_candidate or self.visible_symptoms
        ):
            raise ValueError("out-of-domain observations cannot claim crop or symptoms")
        return self


class VisualAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["visual-observation-v1"] = SCHEMA_VERSION
    analyzer_id: str = Field(min_length=1, max_length=100)
    observations: list[VisualObservation] = Field(min_length=1, max_length=2)


_SYMPTOM_QUERY_TERMS = {
    "discoloration": "đổi màu",
    "spot": "đốm",
    "lesion": "vết tổn thương",
    "wilting": "héo",
    "curling": "xoăn",
    "hole": "lỗ thủng",
    "mold_like_growth": "lớp mốc nhìn thấy",
    "rot_like_tissue": "mô giống thối",
    "cracking": "nứt",
    "other": "triệu chứng bất thường",
}
_PART_QUERY_TERMS = {
    "leaf": "lá",
    "stem": "thân",
    "fruit": "quả",
    "flower": "hoa",
    "root": "rễ",
    "whole_plant": "toàn cây",
    "multiple": "nhiều bộ phận",
}


def validate_analysis_image_scope(
    result: VisualAnalysisResult, expected_image_ids: set[str]
) -> None:
    observed_ids = [observation.image_id for observation in result.observations]
    if len(observed_ids) != len(set(observed_ids)):
        raise ValueError("visual analysis contains duplicate image ids")
    if set(observed_ids) != expected_image_ids:
        raise ValueError("visual analysis image ids do not match validated inputs")


def build_visual_retrieval_query(
    question: str, observations: list[VisualObservation | dict]
) -> str:
    terms: list[str] = []
    for raw_observation in observations:
        observation = (
            raw_observation
            if isinstance(raw_observation, VisualObservation)
            else VisualObservation.model_validate(raw_observation)
        )
        if (
            observation.relevance != "agriculture_plant"
            or observation.confidence < 0.60
        ):
            continue
        if observation.crop_candidate:
            terms.append(observation.crop_candidate)
        part = _PART_QUERY_TERMS.get(observation.plant_part)
        if part:
            terms.append(part)
        for symptom in observation.visible_symptoms:
            if symptom.confidence < 0.55:
                continue
            terms.append(_SYMPTOM_QUERY_TERMS[symptom.symptom_type])
            terms.append(symptom.description)

    unique_terms = list(dict.fromkeys(" ".join(term.split()) for term in terms if term))
    if not unique_terms:
        return question
    suffix = "; ".join(unique_terms)
    return f"{question} Quan sát thị giác: {suffix}"[:1000]
