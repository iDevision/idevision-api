import pathlib
import uuid
import os

import asyncpg
from aiohttp import web

from utils.ratelimit import ratelimit
from utils.rtfm import DocReader
from utils import ocr, utils

reader = DocReader()
router = web.RouteTableDef()

@router.get("/api/public/rtfs")
@ratelimit(3, 5)
async def do_rtfs(request: utils.TypedRequest, _: asyncpg.Connection):
    query = request.query.get("query", None)
    if query is None:
        return web.Response(status=400, reason="Mising query parameter")
    lib = request.query.get("library", '').lower()
    if not lib:
        return web.Response(status=400, reason="Missing library parameter")

    try:
        v = await request.app.rtfs.get_query(lib, query)
        if v is None:
            return web.Response(status=400, reason="library not found. If you think it should be added, contact IAmTomahawkx#1000 on discord.")
        else:
            return v
    except RuntimeError:
        return web.Response(status=500, reason="Source index is not complete, try again later")

@router.get("/api/public/rtfm")
@ratelimit(3, 5)
async def do_rtfm(request: utils.TypedRequest, _: asyncpg.Connection):
    show_labels = request.query.get("show-labels", "true").lower() == "true"
    label_labels = request.query.get("label-labels", "false").lower() == "true"

    location = request.query.get("location", None)
    if location is None:
        return web.Response(status=400, reason="Missing location parameter (The URL of the documentation)")

    query = request.query.get("query", None)
    if query is None:
        return web.Response(status=400, reason="Mising query parameter")
    return await reader.do_rtfm(request, location.strip("/"), query, show_labels, label_labels)

@router.get("/api/public/ocr")
@ratelimit(2, 10)
async def do_ocr(request: utils.TypedRequest, _: asyncpg.Connection):
    if not request.user:
        r = "You need an API key in the Authorization header to use this endpoint. Please refer to https://idevision.net/docs for info on how to get one"
        return web.Response(reason=r, status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "public.ocr"):
        return web.Response(reason="401 Unauthorized", status=401)

    try:
        reader = await request.multipart()
    except AssertionError:
        return web.Response(status=400, reason="Expected a Multipart request")

    data = await reader.next()
    try:
        extension = data.filename.split(".").pop().replace("/", "")
    except:
        return web.Response(status=400, reason="Invalid/No filename provided")

    name = ('%032x' % uuid.uuid4().int)[:8] + "." + extension
    pth = pathlib.Path(f"../tmp/{name}")
    buffer = pth.open("wb")
    while True:
        try:
            chunk = await data.read_chunk()
            if not chunk:
                break
            buffer.write(chunk)
        except:
            pass

    buffer.close()

    response = await ocr.do_ocr(pth, request.app.loop)
    os.remove(pth)
    return web.json_response({"data": response})
