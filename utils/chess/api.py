from aiohttp import web

from .models import Board, BoardValidationError, BadMove
from .render import draw

route = web.RouteTableDef()

@route.post("/chess")
async def new_chess(request: web.Request):
    try:
        data = await request.json()
        wtheme = data.get("white-theme", "wood")
        btheme = data.get("black-theme", "wood")
        boardtheme = data.get("board-theme", "walnut")
    except:
        wtheme = btheme = "wood"
        boardtheme = "walnut"

    try:
        board = Board.new(wtheme, btheme, boardtheme)
    except BoardValidationError as e:
        return web.Response(status=400, reason=e.args[0])

    return web.json_response(board.to_dict())

@route.post("/chess/turn")
async def do_move(request: web.Request):
    data = await request.json()
    try:
        if not all(x in data for x in ("move", "move-turn", "board")):
            raise BoardValidationError("Expected keys 'move', 'move-turn', and 'board' in body")

        board = Board.from_dict(data['board'])
    except BoardValidationError as e:
        return web.Response(status=400, reason=e.args[0])

    move = data['move']
    turn = data['move-turn'].lower() == "white"
    data = {}
    try:
        d = board.make_move(move, turn)
        if d[0]:
            data['arrow'] = ["".join((x[0], str(x[1]))) for x in d[2]]
        else:
            print(d)
    except BadMove as e:
        return web.json_response({"board": board.to_dict(), "error": e.args[0]}, status=417, reason="Expectation Failed")

    data['board'] = board.to_dict()

    return web.json_response(data)

@route.post("/chess/render")
async def render(request: web.Request):
    data = await request.json()
    try:
        board = Board.from_dict(data['board'])
    except BoardValidationError as e:
        return web.Response(status=400, reason=e.args[0])

    arrow = data.get("arrow", None)
    return web.Response(body=draw(board, arrow))

@route.post("/chess/transcript")
async def transcript(request: web.Request):
    data = await request.json()
    try:
        board = Board.from_dict(data['board'])
    except BoardValidationError as e:
        return web.Response(status=400, reason=e.args[0])

    return web.Response(body=board.build_transcript())

app = web.Application()
app.add_routes(route)
#web.run_app(app, host="127.0.0.1", port=1234)