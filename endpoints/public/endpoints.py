import pathlib
import time
import uuid
import os

import asyncpg
from aiohttp import web

from utils.ratelimit import ratelimit
from utils import mathparser
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
    query = request.query.get("search", None)
    if not query:
        return web.Response(reason="Missing 'search' query parameter", status=400)

    return await request.app.xkcd.search_xkcd(query, request)

@router.put("/api/public/xkcd/tags")
@ratelimit(1, 10)
async def put_xkcd_tag(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="You must log in to add tags to comics", status=401)

    try:
        data = await request.json()
        tag = str(data['tag']).lower()
        num = int(data['num'])
    except KeyError as e:
        return web.Response(reason=f"Missing '{e.args[0]}' key from json payload", status=400)
    except:
        return web.Response(reason="Bad JSON payload", status=400)

    d = await conn.fetchval("SELECT num FROM xkcd WHERE $1 = ANY(extra_tags)", tag)
    if d:
        return web.Response(reason=f"Tag '{tag}' is already bound to xkcd #{d}")

    if not await conn.fetchval("UPDATE xkcd SET extra_tags = array_append(extra_tags, $1) WHERE num = $2 RETURNING num", tag, num):
        return web.Response(reason=f"comic #{num} does not exist", status=400)

    request.app.xkcd._cache.clear()
    return web.Response(status=204)

@router.post("/api/public/math")
@ratelimit(2, 6)
async def math(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="You must log in to use beta endpoints", status=401)

    data = await request.text()

    lex = mathparser.MathLexer()
    try:
        start = time.time()
        tokens = lex.tokenize(data)
        lex_time = time.time() - start
    except mathparser.UserInputError as f:
        return web.Response(text=str(f), status=417)

    parser = mathparser.Parser(data, lex)
    try:
        start = time.time()
        exprs = parser.parse(tokens)
        parse_time = time.time()-start
    except mathparser.UserInputError as f:
        return web.Response(text=str(f), status=417)

    resp = ""
    start = time.time()

    for i, expr in enumerate(exprs):
        resp += f"[{i + 1}] {expr.execute(parser)}\n"

    eval_time = time.time() - start

    return web.json_response(
        {
            "output": resp,
            "lex_time": lex_time,
            "parse_time": parse_time,
            "evaluation_time": eval_time
        }
    )