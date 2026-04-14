from pydantic import BaseModel, model_validator, Field, ConfigDict, PlainSerializer, BeforeValidator
from typing import Optional, Any, Literal, Annotated
import numpy as np
import numpy.typing as npt
import json
from django.conf import settings

all_vector_formats: dict[str, dict] = json.load(open('analysis/vector_format.json'))
VECTOR_FORMAT = all_vector_formats[settings.VECTOR_VERSION]

dt = settings.CLASS_MAPPING[VECTOR_FORMAT['format']['dtype']]
PositionVector = npt.NDArray[dt]
DiffVector = PositionVector

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
    variations: list[PV] = Field(default_factory=list)
    notes: dict[str, Any] = Field(default_factory=dict)
    
class Cluster(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    V: SerializablePositionVector
    E: Evaluation
    idx: int

class TacticalDetectionResult(BaseModel):
    label: str
    confidence: float

class TacticalPipelineResult(BaseModel):
    tactic: str
    position: str
    confidence: float
    engine_line: list[str]

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
    E_gap: int
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
    fifty_move_rule: Optional[int] = None
    repetition: Optional[list[int]] = None
    positions: list[Position] = Field(default_factory=list)
    analysis: list[FullPositionResult]



