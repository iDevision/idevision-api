import pathlib
import time
import uuid
import os
import subprocess
import re

import asyncpg
import mathparser
from aiohttp import web

import utils.rtfm
from utils.handler import ratelimit
from utils import ocr, app
from ..cdn.cdn import upload_media_to_slaves

DOCRS_RE = re.compile(r"https://docs\.rs/([^/]*)")
router = web.RouteTableDef()

@router.get("/api/public/rtfs")
@ratelimit(3, 5)
async def do_rtfs(request: app.TypedRequest, _: asyncpg.Connection):
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
        v = request.app.rtfs.get_query(lib, query, fmt=="source")
        if v is None:
            return web.Response(status=400, reason="library not found. If you think it should be added, contact IAmTomahawkx#1000 on discord.")
        else:
            return v
    except RuntimeError:
        return web.Response(status=500, reason="Source index is not complete, try again later")

@router.get("/api/public/rtfm")
@router.get("/api/public/rtfm.sphinx")
@ratelimit(3, 5)
async def do_rtfm_sph(request: app.TypedRequest, _: asyncpg.Connection):
    show_labels = request.query.get("show-labels", "true").lower() == "true"
    label_labels = request.query.get("label-labels", "false").lower() == "true"

    location = request.query.get("location", None)
    if location is None:
        return web.Response(status=400, reason="Missing location parameter (The URL of the documentation)")

    query = request.query.get("query", None)
    if query is None:
        return web.Response(status=400, reason="Mising query parameter")
    return await request.app.rtfm.do_rtfm(request, location.strip("/"), query, show_labels, label_labels)

@router.get("/api/public/rtfm.rustdoc")
@ratelimit(3, 5)
async def do_rtfm_rs(request: app.TypedRequest, _: asyncpg.Connection):
    location = request.query.get("location", None)
    if location is None:
        return web.Response(status=400, reason="Missing location parameter (The URL of the documentation, or 'std')")

    if location == "std":
        location = "https://doc.rust-lang.org/std"
    crate = DOCRS_RE.search(location)
    if not crate:
        return web.Response(status=400, reason="Invalid location (must be a docs.rs crate)")

    crate = crate.groups()[0]

    query = request.query.get("query", None)
    if query is None:
        return web.Response(status=400, reason="Missing query parameter")

    try:
        return await request.app.cargo_rtfm.do_rtfm(request, crate, query)
    except utils.rtfm.ItsFuckingDead:
        return web.Response(status=501, reason="This crate has updated to the new rustdoc format. Please see "
                                               "https://canary.discord.com/channels/514232441498763279/696112877387382835/847717237661237289 "
                                               "(https://discord.gg/Bf5jMRKtD3) for an explanation on this")

@router.get("/api/public/ocr")
@ratelimit(2, 10)
async def do_ocr(request: app.TypedRequest, _: asyncpg.Connection):
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
async def xkcd(request: app.TypedRequest, conn: asyncpg.Connection):
    query = request.query.get("search", None)
    if not query:
        return web.Response(reason="Missing 'search' query parameter", status=400)

    return await request.app.xkcd.search_xkcd(query, request)

@router.put("/api/public/xkcd/tags")
@ratelimit(1, 10)
async def put_xkcd_tag(request: app.TypedRequest, conn: asyncpg.Connection):
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
async def math(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="You must log in to use beta endpoints", status=401)

    data = await request.text()

    lex = mathparser.MathLexer()
    try:
        start = time.time()
        tokens = list(lex.tokenize(data))
        lex_time = time.time() - start
        parser = mathparser.Parser(data, lex)
        start = time.time()
        exprs = parser.parse(tokens)
        parse_time = time.time()-start

        resp = ""
        images = []

        for i, expr in enumerate(exprs):
            try:
                e = expr.execute(None, parser)
            except ZeroDivisionError:  # this one is intentionally left unhandled
                resp += f"[{i + 1}] Zero divison error"
                continue

            if isinstance(e, dict):
                f = await mathparser.graph.plot(e, i + 1)
                if f:
                    images.append(f)

                resp += f"[{i + 1}] See graph {i + 1} ({e})\n"
            else:
                resp += f"[{i + 1}] {e}\n"

    except mathparser.UserInputError as e:
        return web.Response(text=str(e), status=417)

    imgs = []
    if images:
        node = list(filter(lambda x: x['name'] == "math", request.app.slaves.values()))
        if node:
            node = node[0]
            for img in images:
                stat, _resp = await upload_media_to_slaves(
                    request.app,
                    node,
                    img,
                    "image/png",
                    "upload.png",
                    conn,
                    "_internal"
                )
                if stat:
                    imgs.append(_resp)

    eval_time = time.time() - start
    return web.json_response({
        "text": resp,
        "images": imgs,
        "lex_time": lex_time,
        "parse_time": parse_time,
        "evaluation_time": eval_time
    })

@router.put("/api/public/rtfs.reload")
@ratelimit(0, 0, "public.rtfs.reload")
async def reload_rtfs(request: app.TypedRequest, _) -> web.Response:
    perms, admin = request.user['permissions'], "administrator" in request.user['permissions']

    if not admin and "public.rtfs.reload" not in perms:
        return web.Response(reason="You need the public.rtfs.reload permission to use this endpoint", status=401)

    dirs = os.listdir("repos")
    success = []
    fail = []
    from utils.rtfs import Indexes

    indexer = Indexes()

    for d in dirs:
        try:
            subprocess.run(["/bin/bash", "-c", f"cd repos/{d} && git pull"])
        except:
            fail.append(d)
        else:
            success.append(d)

    await indexer._do_index()
    request.app.rtfs = indexer

    return web.json_response({
        "success": success,
        "fail": fail,
        "commits": {name: value.commit for name, value in indexer.index}
    })