"""Pydantic models for the cognitive challenge framework."""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

PyramidLevel = Literal[
    "faits_observables",
    "lois_relations",
    "schemes_operatoires",
    "principes_generateurs",
    "structures_abstraites",
    "metacadres_theoriques",
]

KnowledgeObjectType = Literal["question", "subtheme", "concept", "theme"]


class CognitiveOperationDto(BaseModel):
    key: str
    family: str
    label_fr: str
    label_en: str
    definition_fr: str
    definition_en: str
    evaluates_fr: str
    evaluates_en: str
    pyramid_levels: list[str]
    examples: list[dict[str, Any]] = Field(default_factory=list)


class GameMechanicDto(BaseModel):
    key: str
    label_fr: str
    label_en: str
    description_fr: str
    description_en: str
    advantages_fr: str
    limitations_fr: str
    compatible_operations: list[str]
    compatible_pyramid_levels: list[str]


class CompatibilityEntryDto(BaseModel):
    operation: str
    mechanic: str
    score: int


class PyramidGuidanceDto(BaseModel):
    pyramid_level: str
    operations: list[str]
    mechanics: list[str]
    challenge_types: list[str]
    indicators: list[str]


class CreateChallengePayload(BaseModel):
    title: str
    pyramid_level: PyramidLevel
    cognitive_operation: str
    game_mechanic: str
    knowledge_object_type: KnowledgeObjectType = "question"
    knowledge_object_id: int = Field(..., description="Identifiant générique id_objet")
    difficulty: int = Field(default=2, ge=1, le=5)
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    evaluated_competencies: list[dict[str, Any]] = Field(default_factory=list)
    prerequisites: list[dict[str, Any]] = Field(default_factory=list)
    typical_errors: list[dict[str, Any]] = Field(default_factory=list)
    performance_indicators: list[str] = Field(default_factory=list)
    generation_rules: dict[str, Any] = Field(default_factory=dict)
    content_payload: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published"] = "draft"


class GenerateExercisePayload(BaseModel):
    knowledge_object_type: KnowledgeObjectType = "question"
    knowledge_object_id: int
    pyramid_level: PyramidLevel
    cognitive_operation: str
    game_mechanic: Optional[str] = None
    auto_select_mechanic: bool = Field(
        default=False,
        description="Choisir automatiquement la mécanique via la matrice (score max au 1er défi).",
    )
    difficulty: int = Field(default=2, ge=1, le=5)
    id_user: Optional[int] = None
    variant: Optional[str] = None
    use_ai: Optional[bool] = Field(
        default=None,
        description="True=IA Mistral, False=règles, None=auto (IA si MISTRAL_API_KEY)",
    )
    lang: Optional[str] = Field(default=None, description="Langue UI pour le prompt IA (fr|en)")


class SaveExercisePayload(BaseModel):
    title: Optional[str] = None
    status: Literal["draft", "published"] = "published"


class SubmitAttemptPayload(BaseModel):
    id_exercise: int
    learner_actions: dict[str, Any]
    duration_ms: int = Field(default=0, ge=0)
    id_user: Optional[int] = None


class CheckSortingLabPlacementPayload(BaseModel):
    item_id: str
    category_id: str


class CheckKnowledgeBridgesLinkPayload(BaseModel):
    source_id: str
    target_id: str


class CheckMissingFragmentPayload(BaseModel):
    gap_id: str
    fragment_id: str


class CheckTransformAtelierPayload(BaseModel):
    tool_id: str
    step_index: int = 0


class ChallengeDto(BaseModel):
    id_challenge: int
    title: str
    pyramid_level: str
    cognitive_operation: str
    game_mechanic: str
    knowledge_object_type: str
    knowledge_object_id: int
    difficulty: int
    success_criteria: dict[str, Any]
    evaluated_competencies: list[dict[str, Any]]
    prerequisites: list[dict[str, Any]]
    typical_errors: list[dict[str, Any]]
    performance_indicators: list[str]
    generation_rules: dict[str, Any]
    content_payload: dict[str, Any]
    status: str


class ExerciseDto(BaseModel):
    id_exercise: int
    id_challenge: Optional[int] = None
    id_user: Optional[int] = None
    knowledge_object_type: str
    knowledge_object_id: int
    pyramid_level: str
    cognitive_operation: str
    game_mechanic: str
    difficulty: int
    content: dict[str, Any]
    success_criteria: dict[str, Any]
    status: str
    compatibility_score: Optional[int] = None
    is_first_for_question: bool = False


class EvaluationReservoirDto(BaseModel):
    id_record: int
    id_user: Optional[int] = None
    knowledge_object_type: str
    knowledge_object_id: int
    pyramid_level: str
    cognitive_operation: str
    game_mechanic: str
    compatibility_score: int
    is_first_challenge: bool
    id_exercise: Optional[int] = None
    id_attempt: Optional[int] = None
    id_evaluation: Optional[int] = None
    score: float
    passed: bool
    xp_gained: int
    mastery_delta: float
    duration_ms: int
    feedback: dict[str, Any]
    criteria_results: dict[str, Any]
    dashboard_tags: list[str] = Field(default_factory=list)
    created_at: Optional[str] = None


class AttemptResultDto(BaseModel):
    id_attempt: int
    id_evaluation: int
    score: float
    passed: bool
    mastery_delta: float
    xp_gained: int
    feedback: dict[str, Any]
    criteria_results: dict[str, Any]
