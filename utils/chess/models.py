import itertools
import re
import os
import pathlib
import string
from typing import Tuple, List, Dict, Optional

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
THEMES_DIRS = os.path.join(MEDIA_DIR, "pieces")
BOARDS_DIR = os.path.join(MEDIA_DIR, "boards")
THEMES = os.listdir(THEMES_DIRS)
BOARDS = [x.replace(".png", "") for x in os.listdir(BOARDS_DIR)]
MOVERE = re.compile(r"([a-hA-H][1-8])\s*[-~/|=>]*\s*([a-hA-H][1-8])")

class BoardValidationError(Exception):
    pass

class BadMove(Exception):
    pass

class NotYourMove(BadMove):
    pass


index = {
    0: "pawn",
    1: "rook",
    2: "knight",
    3: "bishop",
    4: "queen",
    5: "king"
}
reverse_index = {v: k for k, v in index.items()}

ROWS = list("abcdefgh")

class Piece:
    __slots__ = "name", "position", "white"

    def __init__(self, name: str, position: Tuple[str, int], white: bool):
        self.name = name
        self.position = position
        self.white = white

    def get_asset(self, theme: str) -> pathlib.Path:
        return pathlib.Path(THEMES_DIRS, theme, f"{'w_' if self.white else 'b_'}{self.name}.png")

    @property
    def type(self):
        return self.name + str(self.white)

    def serialize(self):
        return f"{reverse_index[self.name]}{self.position[0]}{self.position[1]+1}{1 if self.white else 0}"

    @classmethod
    def deserialize(cls, data: str):
        self = cls.__new__(cls)
        self.name = index[int(data[0])]
        self.position = (data[1], int(data[2]) - 1)
        self.white = data[3] == "1"
        return self

    def __repr__(self):
        return f"<{'White' if self.white else 'Black'} {self.name} at {self.position[0]}{self.position[1]}>"


class Board:
    __slots__ = ("pieces", "turn", "transcript", "white_theme", "black_theme", "board_theme", "castle")

    def __init__(self, pieces: Dict[str, List[Piece]], turn: int, transcript: Optional[List[str]],
                 castle: List[int], white_theme: str, black_theme: str, board_theme: str):
        self.pieces = pieces
        self.turn = turn
        self.transcript = transcript or []
        self.white_theme = white_theme
        self.black_theme = black_theme
        self.board_theme = board_theme
        self.castle = castle

    def get_asset(self):
        return pathlib.Path(BOARDS_DIR, f"{self.board_theme}.png")

    @classmethod
    def new(cls, white_theme: str = "wood", black_theme: str = "wood", board_theme: str = "walnut"):
        newboard = [
            "1a80", "2b80", "3c80", "4d80", "5e80", "3f80", "2g80", "1h80",
            "0a70", "0b70", "0c70", "0d70", "0e70", "0f70", "0g70", "0h70",
            "0a21", "0b21", "0c21", "0d21", "0e21", "0f21", "0g21", "0h21",
            "1a11", "2b11", "3c11", "4d11", "5e11", "3f11", "2g11", "1h11",
        ]
        if white_theme not in THEMES:
            raise BoardValidationError(f"{white_theme} is not a valid theme (white-theme). Valid themes are: {', '.join(THEMES)}")
        if black_theme not in THEMES:
            raise BoardValidationError(f"{black_theme} is not a valid theme (black-theme). Valid themes are: {', '.join(THEMES)}")
        if board_theme not in BOARDS:
            raise BoardValidationError(f"{board_theme} is not a valid board (board-theme). Valid boards are {', '.join(BOARDS)}")

        board = {x: [None for _ in range(1, 9)] for x in ROWS}
        for p in newboard:
            p = Piece.deserialize(p)
            board[p.position[0]][p.position[1] - 1] = p

        return cls(board, 1, None, [1, 1, 1, 1], white_theme, black_theme, board_theme)

    @classmethod
    def from_dict(cls, data: dict):
        if "pieces" not in data:
            raise BoardValidationError("pieces not given")

        if not isinstance(data["pieces"], list):
            raise BoardValidationError("pieces was not an array")

        board = {x: [None for _ in range(1, 9)] for x in "abcdefgh"}
        for n, p in enumerate(data["pieces"]):
            if p is None:
                continue
            try:
                p = Piece.deserialize(p)
                if p.position[0] not in "abcdefgh" or 8 <= p.position[1] <= 0:
                    raise BoardValidationError(f"pieces.{n}: invalid position")

            except BoardValidationError:
                raise
            except:
                raise BoardValidationError(f"pieces.{n}: invalid piece")

            if board[p.position[0]][p.position[1]] is not None:
                raise BoardValidationError(f"pieces.{n}: multiple pieces on space {p.position[0]}{p.position[1]} "
                                           f"(found {board[p.position[0]][p.position[1]]} and tried to put {p})")

            board[p.position[0]][p.position[1]] = p

        transcript = data.get("transcript")
        if transcript is not None and not isinstance(transcript, list):
            raise BoardValidationError("transcript: expected an array of strings")

        white_theme = data.get("white-theme", "classic")
        if white_theme not in THEMES:
            raise BoardValidationError(f"white-theme: Invalid theme")

        black_theme = data.get("black-theme", "classic")
        if black_theme not in THEMES:
            raise BoardValidationError(f"black-theme: Invalid theme")

        board_theme = data.get("board-theme", "walnut")
        if board_theme not in BOARDS:
            raise BoardValidationError(f"board-theme: Invalid theme")

        castling = data.get("castling", "0000")
        try:
            castling = [int(x) for x in castling]
            assert all(0 <= x <= 1 for x in castling)
        except:
            raise BoardValidationError(f"castling: invalid castling string")

        return cls(board, data.get("turn", 1), transcript, castling, white_theme, black_theme, board_theme)

    def to_dict(self):
        return {
            "pieces": [p.serialize() if p else None for p in itertools.chain(*self.pieces.values())],
            "turn": self.turn,
            "transcript": self.transcript,
            "white-theme": self.white_theme,
            "black-theme": self.black_theme,
            "board-theme": self.board_theme,
            "castling": "".join(str(x) for x in self.castle)
        }

    def make_move(self, move: str, turn: str):
        if turn is not None:
            if turn == "black" and not self.turn:
                raise NotYourMove("It is white's turn, not black's")
            elif turn == "white" and self.turn:
                raise NotYourMove("It is black's turn, not white's")

        match = MOVERE.match(move)
        if not match:
            raise BadMove(move)

        groups = self._get_groups(*match.groups())
        resp = self.validate_movement(
            *match.groups(), *groups[0], *groups[1], is_moving=True
        )
        if not resp:
            raise BadMove("This move is illegal")

        target = None
        if resp:
            target = self.pieces[groups[1][0]][groups[1][1] - 1]
            
            if target.name == "king":
                check, reason = self._check_for_check(target.white)
                
                if check: raise BadMove(reason)
            
            piece = self.pieces[groups[0][0]][groups[0][1] - 1]
            if piece.name == "king":
                if piece.white:
                    self.castle[0] = self.castle[1] = 0
                else:
                    self.castle[2] = self.castle[3] = 0

            elif piece.name == "rook" and piece.position in (("a", 0), ("h", 0), ("a", 7), ("h", 7)):
                if piece.white and piece.position == ("a", 0):
                    self.castle[0] = 0
                elif piece.white and piece.position == ("h", 0):
                    self.castle[1] = 0
                elif not piece.white and piece.position == ("a", 7):
                    self.castle[2] = 0
                elif not piece.white and piece.position == ("h", 7):
                    self.castle[3] = 0

            self.pieces[groups[0][0]][groups[0][1] - 1] = None  # noqa
            self.pieces[groups[1][0]][groups[1][1] - 1] = piece
            piece.position = groups[1][0], groups[1][1] - 1

            if piece.position[1] in {0, 7} and piece.name == "pawn":
                piece.name = "queen"

            trs = f"{self.turn}{reverse_index[piece.name]}{groups[0][0]}{groups[0][1]}{groups[1][0]}{groups[1][1]}"
            if target:
                trs += f"{reverse_index[target.name]}{int(target.white)}"
            else:
                trs += "nn"

            self.transcript.append(trs)
            self.turn = int(not self.turn)

        return resp, target, groups

    def _get_groups(self, from_: str, to: str) -> Tuple[Tuple[str, int], Tuple[str, int]]:
        x0, y0 = from_[0].lower(), int(from_[1])
        if x0 not in "abcdefgh":
            raise ValueError("unexpected movefrom column")
        if 0 >= y0 > 8:
            raise ValueError("unexpected movefrom row")

        x1, y1 = to[0].lower(), int(to[1])
        if x1 not in "abcdefgh":
            raise ValueError("unexpected moveto column")
        if 0 >= y1 > 8:
            raise ValueError("unexpected moveto row")
        return (x0, y0), (x1, y1)

    def _check_for_check(self, white: bool) -> Tuple[bool, str]:
        # Returns true if in check

        opposite_pieces = self._find_all_pieces(not white)
        kingpos = self._find_king(white)

        for pos, piece in opposite_pieces.items():
            match = MOVERE.match(f"{pos[0]}{pos[1]+1}-{kingpos[0]}{kingpos[1]+1}")
            groups = self._get_groups(*match.groups())
            if self.validate_movement(*match.groups(), *groups[0], *groups[1], is_moving=True):
                return True, f"This move would put the king in check by {piece.name} at {''.join(piece.position)}"
        return False, ""

    def _find_all_pieces(self, white: bool) -> Dict[Tuple[str, int], Piece]:
        return {
            p.position: p
            for p in itertools.chain(*self.pieces.values())
            if p.white == white
        }

    def _find_king(self, white: bool) -> Tuple[str, int]:
        return [
            p.position
            for p in itertools.chain(*self.pieces.values())
            if p.white == white and p.name == "king"
        ][0]

    def build_transcript(self):
        decompressed = ""
        for x in self.transcript:
            dec = ""
            if x[0] == "1":
                dec += "White: "
            else:
                dec += "Black: "
            dec += index[int(x[1])].capitalize()
            dec += f" from {x[2]}{x[3]} to {x[4]}{x[5]}"
            if x[6] != "n":
                dec += f", capturing {'a' if x not in (4,5) else 'the'} {'white' if int(x[1]) else 'black'} {index[int(x[6])].capitalize()}"

            dec += "\n"

            decompressed += dec

        return decompressed

    def validate_movement(self, from_: str, _: str, x0: str, y0: int, x1: str, y1: int, *, is_moving=False) -> bool:
        if (x0, y0) == (x1, y1):
            return False

        piece = self.pieces[x0][y0 - 1]
        if piece is None:
            raise BadMove(f"No piece on {from_}")

        target = self.pieces[x1][y1 - 1]
        if (target is not None and target.white == piece.white and piece.name != "king" and target.name != "rook"):
            return False

        if piece.name == "pawn":
            if x0 != x1:
                if self.turn:
                    return (y1 == y0 + 1 and self.pieces[x1][y1 - 1] is not None and x1 in (ROWS[ROWS.index(x0) - 1] if x0 != "a" else None, ROWS[ROWS.index(x0) + 1] if x0 != "h" else None))

                return (y1 == y0 - 1 and self.pieces[x1][y1 - 1] is not None and x1 in (ROWS[ROWS.index(x0) - 1] if x0 != "a" else None, ROWS[ROWS.index(x0) + 1] if x0 != "h" else None,))

            if self.turn:
                return (y1 == y0 + 1 if y0 != 2 else y1 in (y0 + 1, y0 + 2)) and self.pieces[x1][y1 - 1] is None

            return (y1 == y0 - 1 if y0 != 7 else y1 in (y0 - 1, y0 - 2)) and self.pieces[x1][y1 - 1] is None

        elif piece.name == "rook":
            if x0 != x1 and y0 != y1:
                return False

            elif x0 != x1:
                idx0, idx1 = ROWS.index(x0) + 1, ROWS.index(x1) + 1
                if idx0 > idx1:
                    sl = [x[y0] for i, x in self.pieces.items() if idx0 > ROWS.index(i) + 1 > idx1]
                else:
                    sl = [x[y0] for i, x in self.pieces.items() if idx0 < ROWS.index(i) + 1 < idx1]

                return not any(sl)
            else:
                if y0 > y1:
                    sl = self.pieces[x0][y1 : y0 - 1]
                else:
                    sl = self.pieces[x0][y0 : y1 - 1]

                return not any(sl)

        elif piece.name == "bishop":
            if x0 == x1 or y0 == y1:
                return False

            idx0, idx1 = ROWS.index(x0) + 1, ROWS.index(x1) + 1
            targets = []
            modx, mody = 1 if idx0 < idx1 else -1, 1 if y1 > y0 else -1
            nx, ny = idx0 - 1, y0 - 1
            while ny != y1 - 1:
                nx += modx
                ny += mody
                if nx < 0 or ny < 0:
                    return False

                targets.append(self.pieces[string.ascii_lowercase[nx]][ny])

            if idx0 > idx1:
                return y1 in (y0 + (idx0 - idx1), y0 - (idx0 - idx1)) and not any(targets)

            return y1 in (y0 + (idx1 - idx0), y0 - (idx1 - idx0)) and not any(targets)

        elif piece.name == "knight":
            if x0 == x1 or y0 == y1:
                return False
            return (ROWS.index(x0) - ROWS.index(x1), y0 - y1) in (
                (-2, 1), (-2, -1), (-1, 2), (-1, -2),
                (2, 1), (2, -1), (1, 2), (1, -2),
            )
        elif piece.name == "queen":
            if y0 == y1:
                idx0, idx1 = ROWS.index(x0) + 1, ROWS.index(x1) + 1
                if idx0 > idx1:
                    sl = [x[y0] for i, x in self.pieces.items() if idx0 > ROWS.index(i) + 1 > idx1]
                else:
                    sl = [x[y0] for i, x in self.pieces.items() if idx0 < ROWS.index(i) + 1 < idx1]
                return all(x is None for x in sl)

            elif x0 == x1:
                if y0 > y1:
                    sl = self.pieces[x0][y1:y0]
                else:
                    sl = self.pieces[x0][y0:y1]
                return all(x is None for x in sl)
            else:
                idx0, idx1 = ROWS.index(x0) + 1, ROWS.index(x1) + 1
                targets = []
                modx, mody = 1 if idx0 < idx1 else -1, 1 if y1 > y0 else -1
                nx, ny = idx0, y0
                while ny != y1:
                    nx += modx
                    ny += mody
                    targets.append((string.ascii_lowercase[nx], ny))

                if idx0 > idx1:
                    return y1 in (y0 + (idx0 - idx1), y0 - (idx0 - idx1)) and not any(targets)

                return y1 in (y0 + (idx1 - idx0), y0 - (idx1 - idx0)) and not any(targets)

        elif piece.name == "king":
            def _inner():
                if not ((1 > (ROWS.index(x0) - ROWS.index(x1)) > -1) and (1 > y0 - y1 > -1)):

                    if (self.pieces[x1][y1 - 1] is not None and self.pieces[x1][y1 - 1].name == "rook"):
                        shift = 0 if self.turn else 2
                        if x1 < x0:
                            return self.castle[shift] == 1 and not any(x[7 if shift else 0] for i, x in self.pieces.items() if i in "bcd"), shift
                        elif x1 > x0:
                            return  self.castle[shift + 1] == 1 and not any(x[7 if shift else 0] for i, x in self.pieces.items() if i in "fg"), shift + 1,
                        return False, None

                return True, None

            r, castle = _inner()
            if not r or castle is None or not is_moving:
                return r

            cts = {
                0: (("a", 0), ("b", 0)),
                1: (("h", 0), ("g", 0)),
                2: (("a", 7), ("b", 7)),
                3: (("h", 7), ("g", 7)),
            }[castle]
            p = self.pieces[cts[0][0]][cts[0][1]]
            self.pieces[cts[1][0]][cts[1][1]] = p
            self.pieces[cts[0][0]][cts[0][1]] = None  # noqa
            p.position = cts[1]
            return True

        raise ValueError("Unknown piece on board")
