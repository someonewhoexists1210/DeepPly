import chess
from .utils import Position, Evaluation
from typing import Literal

POSSIBLE_TAGS = Literal[
    'fork',
    'pin',
    'anastasia_mate',
    'attraction',
    'back_rank_mate',
    'boden_mate',
    'capturing_defender',
    'clearance',
    'defensive_move',
    'discovered_attack',
    'deflection',
    'double_bishop_mate',
    'double_check',
    "dovetail_mate",
    'equality',
    'en_passant',
    'exposed_king',
    'fork',
    'hanging_piece',
    'hook_mate',
    'interference',
    'intermezzo',
    'overloading',
    'pin',
    'promotion',
    'quiet_move',
    'sacrifice',
    'skewer',
    'smothered_mate',
    'trapped_piece',
    'x_ray',
    'zugzwang'
]

def fork(starting_pos: Position, engine_line: Evaluation):
    pass