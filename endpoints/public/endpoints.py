import pathlib
import uuid
import os

import asyncpg
from aiohttp import web

from utils.ratelimit import ratelimit
from utils.rtfm import DocReader
from utils import ocr, utils

router = web.RouteTableDef()

@router.get("/api/public/rtfs")
@ratelimit(3, 5)
async def do_rtfs(request: utils.TypedRequest, _: asyncpg.Connection):
    fmt = request.query.get("format", "links")
    if fmt not in ("links", "source"):
        return web.Response(status=400, reason="format must be one of 'links' or 'source'")

    query = request.query.get("query", None)

    lib = request.query.get("library", '').lower()

    if query is None and not lib:
        return web.json_response({"libraries": request.app.rtfs.lib_index, "notice": "The 'query' and 'lib' parameters must be provided to preform a search"}, status=200)

    if query is None:
        return web.Response(status=400, reason="Mising query parameter")

    if not lib:
        return web.Response(status=400, reason="Missing library parameter")

    try:
        v = await request.app.rtfs.get_query(lib, query, fmt=="source")
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
    return await request.app.rtfm.do_rtfm(request, location.strip("/"), query, show_labels, label_labels)

@router.get("/api/public/ocr")
@ratelimit(2, 10)
async def do_ocr(request: utils.TypedRequest, _: asyncpg.Connection):
    if not request.user:
        r = "You need an API key in the Authorization header to use this endpoint. Please refer to https://idevision.net/docs for info on how to get one"
        return web.Response(reason=r, status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "public.ocr"):
        return web.Response(reason="401 Unauthorized", status=401)

    ext = request.query.get("filetype", None)
    if ext is None:
        return web.Response(reason="File-Type query arg is required.", status=400)

    try:
        reader = await request.multipart()
        _data = await reader.next()
        async def data():
            while True:
                v = await _data.read_chunk()
                if not v:
                    break
                yield v

    except AssertionError:
        async def data():
            while True:
                v = await request.content.read(32)
                if not v:
                    break

                yield v
    except:
        return web.Response(reason="Invalid multipart request", status=400)

    name = ('%032x' % uuid.uuid4().int)[:8] + "." + ext
    pth = pathlib.Path(f"../tmp/{name}")
    buffer = pth.open("wb")
    try:
        async for chunk in data():
            buffer.write(chunk)
    except:
        pass

    buffer.close()

    response = await ocr.do_ocr(pth, request.app.loop)
    os.remove(pth)
    return web.json_response({"data": response})


@router.get("/api/public/xkcd")
@ratelimit(10, 10)
async def xkcd(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user or not request.user['admin']:
        return web.Response(status=404)

    query = request.query.get("search", None)
    if not query:
        return web.Response(reason="Missing 'search' query parameter", status=400)

    return await request.app.xkcd.search_xkcd(query, request)