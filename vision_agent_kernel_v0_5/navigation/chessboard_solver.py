"""E-41: Chessboard puzzle solver for desert ruins.

Solves chessboard puzzles found in Sumeru desert ruins.
These puzzles require moving chess pieces to specific positions.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

log = logging.getLogger(__name__)


class ChessPieceType(str, Enum):
    ROOK = "rook"
    KNIGHT = "knight"
    BISHOP = "bishop"
    QUEEN = "queen"
    KING = "king"
    PAWN = "pawn"


class PlayerColor(str, Enum):
    WHITE = "white"
    BLACK = "black"


@dataclass(frozen=True, slots=True)
class ChessSquare:
    """A single square on the chessboard."""
    row: int  # 0-7
    col: int  # 0-7
    piece: ChessPieceType | None = None
    color: PlayerColor | None = None


@dataclass(frozen=True, slots=True)
class ChessMove:
    """A move to solve the puzzle."""
    from_row: int
    from_col: int
    to_row: int
    to_col: int
    piece: ChessPieceType


@dataclass(frozen=True, slots=True)
class ChessboardPuzzle:
    """A chessboard puzzle to solve."""
    initial_state: list[list[ChessSquare | None]]  # 8x8 grid
    target_state: list[list[ChessSquare | None]] | None  # Optional target pattern
    moves: list[ChessMove]
    solved: bool = False


class ChessboardSolver:
    """Solve chessboard puzzles in desert ruins."""

    # Chess piece movement patterns
    _MOVES: dict[ChessPieceType, list[tuple[int, int]]] = {
        ChessPieceType.ROOK: [(0, 1), (0, -1), (1, 0), (-1, 0)],
        ChessPieceType.BISHOP: [(1, 1), (1, -1), (-1, 1), (-1, -1)],
        ChessPieceType.QUEEN: [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)],
        ChessPieceType.KNIGHT: [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)],
        ChessPieceType.KING: [(0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)],
        ChessPieceType.PAWN: [(1, 0), (1, 1), (1, -1)],
    }

    def __init__(self) -> None:
        self._current_state: list[list[ChessSquare | None]] | None = None

    def parse_board(
        self, board_image: np.ndarray, frame_id: int = 0
    ) -> list[list[ChessSquare | None]]:
        """Parse chessboard from image.

        Args:
            board_image: Image of the chessboard
            frame_id: Current frame ID

        Returns:
            8x8 grid of ChessSquare or None
        """
        # Initialize empty board
        board: list[list[ChessSquare | None]] = [[None] * 8 for _ in range(8)]

        # In production, use VLM or template matching to detect pieces
        # For now, return empty board as placeholder
        self._current_state = board
        return board

    def solve(
        self,
        board: list[list[ChessSquare | None]],
        max_moves: int = 10,
    ) -> ChessboardPuzzle:
        """Find solution for chessboard puzzle.

        Args:
            board: Current board state
            max_moves: Maximum moves to allow

        Returns:
            ChessboardPuzzle with solution moves
        """
        moves: list[ChessMove] = []

        # Simplified solver: try to find adjacent empties for each piece
        for row in range(8):
            for col in range(8):
                square = board[row][col]
                if square is not None and square.piece is not None:
                    # Try to find valid moves
                    valid_moves = self._find_valid_moves(board, row, col, square.piece)
                    if valid_moves:
                        # Take first valid move
                        to_row, to_col = valid_moves[0]
                        moves.append(ChessMove(
                            from_row=row,
                            from_col=col,
                            to_row=to_row,
                            to_col=to_col,
                            piece=square.piece,
                        ))

        return ChessboardPuzzle(
            initial_state=board,
            target_state=None,
            moves=moves,
            solved=len(moves) > 0,
        )

    def _find_valid_moves(
        self,
        board: list[list[ChessSquare | None]],
        row: int,
        col: int,
        piece: ChessPieceType,
    ) -> list[tuple[int, int]]:
        """Find valid moves for a piece at given position."""
        moves: list[tuple[int, int]] = []

        if piece == ChessPieceType.PAWN:
            # Pawns move forward one
            new_row = row + 1
            if 0 <= new_row < 8:
                if board[new_row][col] is None:
                    moves.append((new_row, col))

        elif piece in (ChessPieceType.ROOK, ChessPieceType.BISHOP, ChessPieceType.QUEEN):
            # Sliding pieces
            for dr, dc in self._MOVES[piece]:
                new_row, new_col = row + dr, col + dc
                while 0 <= new_row < 8 and 0 <= new_col < 8:
                    if board[new_row][new_col] is None:
                        moves.append((new_row, new_col))
                    else:
                        # Can capture
                        moves.append((new_row, new_col))
                        break
                    # Rooks and queens continue, bishops stop after one
                    if piece == ChessPieceType.BISHOP:
                        break
                    new_row += dr
                    new_col += dc

        elif piece == ChessPieceType.KNIGHT:
            for dr, dc in self._MOVES[piece]:
                new_row, new_col = row + dr, col + dc
                if 0 <= new_row < 8 and 0 <= new_col < 8:
                    moves.append((new_row, new_col))

        elif piece == ChessPieceType.KING:
            for dr, dc in self._MOVES[piece]:
                new_row, new_col = row + dr, col + dc
                if 0 <= new_row < 8 and 0 <= new_col < 8:
                    moves.append((new_row, new_col))

        return moves

    def execute_move(self, move: ChessMove) -> bool:
        """Execute a move on the current board.

        Args:
            move: The move to execute

        Returns:
            True if successful
        """
        if self._current_state is None:
            return False

        piece = self._current_state[move.from_row][move.from_col]
        if piece is None:
            return False

        # Move piece
        self._current_state[move.to_row][move.to_col] = piece
        self._current_state[move.from_row][move.from_col] = None

        log.info(
            "[Chessboard] Moved %s from (%d,%d) to (%d,%d)",
            move.piece.value, move.from_row, move.from_col, move.to_row, move.to_col
        )
        return True

    def get_next_move(self, puzzle: ChessboardPuzzle) -> ChessMove | None:
        """Get the next move from solution.

        Args:
            puzzle: The puzzle with solution

        Returns:
            Next ChessMove or None if solved
        """
        if not self._current_state:
            return None

        # Return next unexecuted move
        for move in puzzle.moves:
            # Check if this move is still valid (piece hasn't moved since)
            if self._current_state[move.from_row][move.from_col] is not None:
                return move

        return None