from pydantic import BaseModel, model_validator, Field, ConfigDict, PlainSerializer, BeforeValidator
from typing import Optional, Any, Literal, Annotated
import numpy as np
import numpy.typing as npt
import json
from django.conf import settings

all_vector_formats: dict[str, dict] = json.load(open('analysis/vector_format.json'))
VECTOR_FORMAT = all_vector_formats[settings.VECTOR_VERSION]
VECTOR_FEATURES: list[str] = VECTOR_FORMAT['format']['features']

dt = settings.CLASS_MAPPING[VECTOR_FORMAT['format']['dtype']]
PositionVector = npt.NDArray[dt]
DiffVector = PositionVector

def cast_to_typed_float(v: Any) -> float:
    # Cast through the configured numpy dtype to preserve desired precision.
    return float(np.asarray(v, dtype=dt).item())

TypedFloat = Annotated[
    float,
    BeforeValidator(cast_to_typed_float),
    PlainSerializer(cast_to_typed_float, return_type=float),
]

def validate_vector_format(v: Any, format: np.dtype):
    if not isinstance(v, np.ndarray):
        raise ValueError(f"Expected a numpy array for vector, got {type(v)}")
    if v.dtype != format:
        raise ValueError(f"Expected vector of dtype {format}, got {v.dtype}")
    return v

SerializableArray = Annotated[
    np.ndarray, 
    BeforeValidator(lambda x: np.array(x, dtype=dt) if isinstance(x, list) else x),
    PlainSerializer(lambda x: x.tolist(), return_type=list)]
SerializablePositionVector = Annotated[
    PositionVector, 
    BeforeValidator(lambda x: validate_vector_format(x, dt)),
    PlainSerializer(lambda x: x.tolist(), return_type=list)]
SerializableDiffVector = Annotated[
    DiffVector, 
    BeforeValidator(lambda x: validate_vector_format(x, dt)),
    PlainSerializer(lambda x: x.tolist(), return_type=list)
]

class Evaluation(BaseModel):
    score: int
    mate: Optional[int] = None
    cp: Optional[int] = None

    @model_validator(mode='after')
    def check_one(cls, values):
        if (values.mate is None) == (values.cp is None):
            raise ValueError("Exactly one of mate or cp must be provided for Evaluation")
        return values
        
    def __sub__(self, other: "Evaluation") -> int:
        if not isinstance(other, Evaluation):
            return NotImplemented
        return self.score - other.score

class PV(BaseModel):
    line: str
    evaluation: Evaluation

class Position(BaseModel):
    fen: str
    index: int
    move: str
    piece_moved: Optional[str] = None
    engine_move: Optional[str] = None
    engine_piece_moved: Optional[str] = None
    capture: bool = False
    captured_piece: Optional[str] = None
    engine_capture: bool = False
    engine_captured_piece: Optional[str] = None
    variations: list[PV] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)
    
class Cluster(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    V: SerializablePositionVector
    E: Evaluation
    idx: int

class Target(BaseModel):
    square: str
    piece: str
    color: str

class TacticalDetectionResult(BaseModel):
    pattern: str
    color: str
    key_squares: list[str]
    targets: list[Target]
    trigger_move: str


class PositionalPipelineResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    vectors_full: list[tuple[SerializablePositionVector, Optional[SerializablePositionVector]]]
    user_vector: SerializablePositionVector
    engine_vectors: list[SerializablePositionVector]
    clusters: list[list[int]] # List of clusters, each cluster is a list of position indices that belong to that cluster
    cluster_data: list[Cluster]
    plan_distances: SerializableArray
    plan_probabilities: SerializableArray
    user_plan: Cluster
    user_plan_confidence: float
    plan_match: Literal[-1] | Literal[0] | Literal[1] # -1 = no match, 0 = partial match, 1 = full match
    domination: bool
    V_ref: SerializablePositionVector
    V_gap: SerializableDiffVector
    E_ref: Evaluation
    next_position_eval: Evaluation
    is_acceptable_move: bool
    strategic_mistake: bool
    result: str

class FullPositionResult(BaseModel):
    strategic_analysis: PositionalPipelineResult
    tactical_analysis: Optional[TacticalDetectionResult] = None
    critical: bool = False
    overall_mistake: bool = False
    mistake_type: Optional[str] = None

class GameAnalysisResult(BaseModel):
    game_id: int
    player: str
    color: bool
    result: str
    time_control: Optional[str] = None
    fifty_move_rule: Optional[int] = None
    repetition: Optional[list[int]] = None
    positions: list[Position] = Field(default_factory=list)
    analysis: list[FullPositionResult]

class ConditionedCluster(BaseModel):
    RepresentationVector: dict[str, TypedFloat]
    centipawn_evaluation: Optional[int] = None
    mate_evaluation: Optional[int] = None

class ConditionedPositionalPipelineResult(BaseModel):
    most_likely_followed_engine_plan: ConditionedCluster
    does_user_follow_most_likely_plan: Literal["No plan match", "Partial plan match", "Full plan match"]
    does_one_plan_dominate_other_engine_plans: bool
    main_changes: dict[str, str]
    user_mate_score: Optional[int] = None
    user_cp_score: Optional[int] = None
    engine_mate_score: Optional[int] = None
    engine_cp_score: Optional[int] = None
    is_acceptable_move: bool
    is_strategic_mistake: bool
    short_positional_result_summary: str

class ConditionedPosition(BaseModel):
    fen: str
    ply_number: int
    move: str
    piece_moved: Optional[str] = None
    capture: bool = False
    captured_piece: Optional[str] = None
    engine_move: Optional[str] = None
    engine_piece_moved: Optional[str] = None
    engine_capture: bool = False
    engine_captured_piece: Optional[str] = None
    repetition: bool = False
    fifty_move_rule: bool = False

def assert_no_overlap(*models: type[BaseModel]):
    seen = set()
    overlap = set()

    for m in models:
        fields = set(m.model_fields.keys())
        overlap |= seen & fields
        seen |= fields

    assert not overlap, f"Overlapping fields found: {overlap}"


assert_no_overlap(ConditionedPosition, ConditionedPositionalPipelineResult)
class ConditionedFullPositionResult(ConditionedPosition, ConditionedPositionalPipelineResult):
    critical: bool = False
    tactics_present: Optional[TacticalDetectionResult] = None
    overall_mistake: bool = False
    mistake_type: Optional[str] = None

class ExplanationInput(BaseModel):
    player: str
    color: str
    result: str
    time_control: Optional[str] = None
    positions: list[ConditionedFullPositionResult]

class ExplanationPosition(BaseModel):
    ply_number: int
    explanation: str

    model_config = ConfigDict(extra="forbid")

class ExplanationOutput(BaseModel):
    explanations_per_position: list[ExplanationPosition]
    summary: str

    model_config = ConfigDict(extra="forbid")