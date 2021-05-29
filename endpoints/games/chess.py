import asyncpg
from typing import TYPE_CHECKING
from aiohttp import web
from utils.chess import api
from utils.handler import ratelimit

if TYPE_CHECKING:
    from utils.app import TypedRequest, App

router = web.RouteTableDef()

def setup(app: "App"):
    app.add_routes(router)

@router.post("/api/games/chess")
@ratelimit(5, 10)
async def new_chess(request: "TypedRequest", _):
    return await api.new_chess(request)

@router.post("/api/games/chess/turn")
@ratelimit(5, 10)
async def turn_chess(request: "TypedRequest", _):
    return await api.do_move(request)

@router.post("/api/games/chess/render")
@ratelimit(5, 10)
async def render_chess(request: "TypedRequest", _):
    return await api.render(request)

@router.post("/api/games/chess/transcript")
@ratelimit(5, 10)
async def render_chess(request: "TypedRequest", _):
    return await api.transcript(request)
