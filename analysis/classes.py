from dataclasses import dataclass, field
from typing import Optional, Any
import chess
import numpy as np
import json
from django.conf import settings

all_vector_formats: dict[str, dict] = json.load(open('analysis/vector_format.json'))
VECTOR_FORMAT = all_vector_formats["v1.0"]

dt = np.float32
PositionVector = np.ndarray[tuple[int], np.dtype[dt]]

@dataclass
class Evaluation:
    score: int
    mate: Optional[int] = None
    cp: Optional[int] = None

    def __post_init__(self):
        if (self.mate is None) == (self.cp is None):
            raise ValueError("Exactly one of mate or cp must be provided for Evaluation")
        
    def __sub__(self, other: "Evaluation") -> int:
        if not isinstance(other, Evaluation):
            return NotImplemented
        return self.score - other.score

@dataclass
class PV:
    line: str
    pv_objs: list[chess.Move] = field(init=False)
    evaluation: Evaluation

@dataclass
class Position:
    fen: str
    index: int
    move: str
    eval: list[PV] = field(default_factory=list)
    notes: dict[str, Any] = field(default_factory=dict)

@dataclass
class Cluster:
    V: PositionVector
    E: Evaluation
    idx: int