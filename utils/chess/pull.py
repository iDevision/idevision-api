import requests
import os

THEMES = [
    "classic",
    "glass",
    "neo",
    "neo_wood",
    "bases",
    "alpha",
    "8_bit",
    "game_room",
    "graffiti",
    "lolz",
    "neon",
    "wood",
    "ocean"
]
BOARDS = [
    "walnut",
    "glass",
    "neon",
    "8_bit",
    "graffiti",
    "green",
    "lolz",
    "overlay",
    "parchment"
]
PIECES = {
    "wp": "w_pawn",
    "wr": "w_rook",
    "wn": "w_knight",
    "wb": "w_bishop",
    "wq": "w_queen",
    "wk": "w_king",
    "bp": "b_pawn",
    "br": "b_rook",
    "bn": "b_knight",
    "bb": "b_bishop",
    "bq": "b_queen",
    "bk": "b_king",
}

session = requests.session()
session.headers['User-Agent'] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:88.0) Gecko/20100101 Firefox/88.0"
session.headers['Origin'] = session.headers['Referer'] = "https://www.chess.com"

if not os.path.exists("./media/pieces"):
    os.mkdir("./media/pieces")

for theme in THEMES:
    if not os.path.exists(f"./media/pieces/{theme}"):
        os.mkdir(f"./media/pieces/{theme}")
    for piece, target in PIECES.items():
        resp = session.get(f"https://images.chesscomfiles.com/chess-themes/pieces/{theme}/150/{piece}.png")
        resp.raise_for_status()
        with open(f"./media/pieces/{theme}/{target}.png", "wb") as f:
            f.write(resp.content)

if not os.path.exists("./media/boards"):
    os.mkdir("./media/boards")

for board in BOARDS:
    resp = session.get(f"https://images.chesscomfiles.com/chess-themes/boards/{board}/150.png")
    resp.raise_for_status()
    with open(f"./media/boards/{board}.png", "wb") as f:
        f.write(resp.content)
