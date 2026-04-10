import chess
import numpy as np
import numpy.typing as npt
from classes import PositionVector, VECTOR_FORMAT, dt



PIECE_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3.25,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0
}

CENTER_SQUARES = [chess.D4, chess.E4, chess.D5, chess.E5]

def all_pieces(board: chess.Board, color: chess.Color) -> list[chess.Square]:
    pieces = []
    for piece_type in chess.PIECE_TYPES:
        pieces.extend(board.pieces(piece_type, color))
    return pieces

def material_counts(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    pawns = len(board.pieces(chess.PAWN, color))
    knights = len(board.pieces(chess.KNIGHT, color))
    bishops = len(board.pieces(chess.BISHOP, color))
    rooks = len(board.pieces(chess.ROOK, color))
    queens = len(board.pieces(chess.QUEEN, color))

    return np.array([pawns, knights, bishops, rooks, queens], dtype=dt)

def total_material(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    return np.array([sum(
        len(board.pieces(piece, color)) * value
        for piece, value in PIECE_VALUES.items()
    )], dtype=dt)

def pawn_features(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    pawns = list(board.pieces(chess.PAWN, color))
    files = {f: [] for f in range(8)}

    for pawn in pawns:
        files[chess.square_file(pawn)].append(pawn)

    iso = 0
    doubled = 0
    backward = 0
    passed = 0
    isl = 0
    central = 0

    prev = -2
    for f in sorted(files.keys()):
        if len(files[f]) > 0:
            if f != prev + 1:
                isl += 1
            prev = f

        if len(files[f]) > 1:
            doubled += len(files[f]) - 1

    for pawn in pawns:
        file = chess.square_file(pawn)
        rank = chess.square_rank(pawn)

        if file in [3, 4]:
            central += 1

        if (file == 0 or len(files[file - 1]) == 0) and (file == 7 or len(files[file + 1]) == 0):
            iso += 1

        adj = []
        for f in [file - 1, file + 1]:
            if 0 <= f <= 7:
                adj.extend(files[f])


        # FUTURE: CHECK LEGAL MOVES FIRST. IF IT IS PINNED, THEN IT IS CURRENTLY BACKWARD
        is_back = True
        for p in adj:
            if color == chess.WHITE and chess.square_rank(p) < rank or \
               color == chess.BLACK and chess.square_rank(p) > rank:
                is_back = False
        
        if is_back:
            square_front = chess.square(file, rank + (1 if color == chess.WHITE else -1))
            if len(board.attackers(not color, square_front)) < len(board.attackers(color, square_front)):
                backward += 1  ## FUTURE: ADD ATTACK CHAIN CHECK

        
        for opp_pawn in board.pieces(chess.PAWN, not color):
            opp_file = chess.square_file(opp_pawn)
            opp_rank = chess.square_rank(opp_pawn)

            if abs(opp_file - file) <= 1:
                if color == chess.WHITE and opp_rank > rank or \
                   color == chess.BLACK and opp_rank < rank:
                    break
        else:
            passed += 1

    
    return np.array([iso, doubled, backward, passed, isl, central], dtype=dt)

def king_area(king_sq: chess.Square) -> list[chess.Square]:
    area = []
    for sq in chess.SQUARES:
        if chess.square_distance(king_sq, sq) <= 2:
            area.append(sq)
    return area

def king_features(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    king_square = board.king(color)
    if king_square is None:
        return np.array([0, 0, 0], dtype=dt)
    
    zone = king_area(king_square)

    ## FUTURE: IMPROVE IMPORTANCE OF PIECE LOCATION
    attackers = sum(len(board.attackers(not color, sq)) for sq in zone)
    defenders = sum(len(board.attackers(color, sq)) for sq in zone)

    pawn_shield = sum(1 for sq in zone if board.piece_at(sq) == chess.PAWN and board.color_at(sq) == color)
    location = chess.square_file(king_square) / 7

    return np.array([attackers, defenders, pawn_shield, location], dtype=dt)

def control_features(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    center = sum(len(board.attackers(color, sq)) for sq in CENTER_SQUARES)

    kingside_files = [5, 6, 7]
    queenside_files = [0, 1, 2]

    kingside_control = 0
    queenside_control = 0
    for sq in chess.SQUARES:
        file = chess.square_file(sq)
        if file in kingside_files:
            kingside_control += len(board.attackers(color, sq))
        elif file in queenside_files:
            queenside_control += len(board.attackers(color, sq))
    
    return np.array([center, kingside_control, queenside_control], dtype=dt)

def pressure_features(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    pressure = 0
    for piece in all_pieces(board, not color):
        if board.piece_at(piece).piece_type == chess.KING: #type:ignore
            continue
        attackers = board.attackers(color, piece)
        defenders = board.attackers(not color, piece)

        if len(attackers) >= len(defenders) - 1: # FUTURE: USE ATTACK MAPS
            pressure += 1

    king_sq = board.king(not color)
    if king_sq is None:
        raise Exception("Invalid board state: no king found")
    
    zone = king_area(king_sq)
    pressure += sum(len(board.attackers(color, sq)) for sq in zone)
    return np.array([pressure], dtype=dt)

def pawn_front_features(board: chess.Board, color: chess.Color) -> npt.NDArray[dt]:
    pawns = list(board.pieces(chess.PAWN, color))

    kingside_files = [5, 6, 7]
    queenside_files = [0, 1, 2]

    kingside_push = 0
    queenside_push = 0
    kingside_count = 0
    queenside_count = 0

    for pawn in pawns:
        file = chess.square_file(pawn)
        rank = chess.square_rank(pawn)

        advance = rank if color == chess.WHITE else (7 - rank)
        if file in kingside_files:
            kingside_push += advance
            kingside_count += 1
        elif file in queenside_files:
            queenside_push += advance
            queenside_count += 1

    return np.array([
        kingside_push,
        queenside_push,
        kingside_count,
        queenside_count
    ], dtype=dt)

def evaluate_side(board: chess.Board, color: chess.Color) -> PositionVector:
    vec =  np.concatenate([
        material_counts(board, color),
        total_material(board, color),
        pawn_features(board, color),
        king_features(board, color),
        control_features(board, color),
        pressure_features(board, color),
        pawn_front_features(board, color)
    ], dtype=dt)

    if vec.shape[0] != len(VECTOR_FORMAT['format']['features']):
        raise ValueError(f"Vector length {vec.shape[0]} does not match expected length {len(VECTOR_FORMAT['format']['features'])}")
    
    return vec

def generate_position_vector(board: chess.Board, color: chess.Color) -> tuple[PositionVector, PositionVector | None]:
    if VECTOR_FORMAT['format']['per_side']:
        white_vec = evaluate_side(board, chess.WHITE)
        black_vec = evaluate_side(board, chess.BLACK)

        return (white_vec, black_vec) if color == chess.WHITE else (black_vec, white_vec)
    return evaluate_side(board, color), None