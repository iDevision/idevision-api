import pathlib
import uuid
import os

from yarl import URL
from aiohttp import web

from ratelimit import ratelimit
from .rtfm import DocReader
from .rtfs import Index
from . import ocr

import utils

import twitchio, discord, wavelink

print("[RTFS] Start indexing")
rtfs_cache = {
    "discord.py": Index(f"https://github.com/Rapptz/discord.py/blob/v{discord.__version__.strip('a')}/").do_index(discord, 1, 3),
    "twitchio": Index(f"https://github.com/TwitchIO/TwitchIO/blob/v{twitchio.__version__.strip('a')}/").do_index(twitchio, 2, 3),
    "wavelink": Index(f"https://github.com/PythonistaGuild/Wavelink/v{wavelink.__version__.strip('a')}/").do_index(wavelink, 3, 3)
}
print("[RTFS] Finish indexing")

reader = DocReader()

router = web.RouteTableDef()

@router.get("/api/public/rtfs")
@ratelimit(3, 5)
async def do_rtfs(request: utils.TypedRequest):
    query = request.query.get("query", None)
    if query is None:
        return web.Response(status=400, reason="Mising query parameter")
    lib = request.query.get("library", '').lower()
    if not lib:
        return web.Response(status=400, reason="Missing library parameter")
    if lib not in rtfs_cache:
        return web.Response(status=400, reason="library parameter must be one of " + ', '.join(rtfs_cache.keys()))

    return await rtfs_cache[lib].do_rtfs(query)

@router.get("/api/public/rtfm")
@ratelimit(3, 5)
async def do_rtfm(request: utils.TypedRequest):
    show_labels = request.query.get("show-labels", None)
    if show_labels is None:
        return web.Response(status=400, reason="Missing show-labels parameter")
    show_labels = show_labels.lower() == "true"

    label_labels = request.query.get("label-labels", None)
    if label_labels is None:
        return web.Response(status=400, reason="Missing label-labels parameter")
    label_labels = label_labels.lower() == "true"
    location = request.query.get("location", None)
    if location is None:
        return web.Response(status=400, reason="Missing location parameter (The URL of the documentation)")
    try:
        location = URL(location)
    except:
        return web.Response(status=400, reason="Invalid location (bad URL)")
    query = request.query.get("query", None)
    if query is None:
        return web.Response(status=400, reason="Mising query parameter")
    return await reader.do_rtfm(str(location), query, show_labels, label_labels)

@router.get("/api/public/ocr")
@ratelimit(1, 5)
async def do_ocr(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="You need an API key in the Authorization header to use this endpoint. Please refer to https://idevision.net/docs for info on how to get one", status=401)

    if not utils.route_allowed(routes, "api/public/ocr"):
        return web.Response(text="401 Unauthorized", status=401)

    reader = await request.multipart()
    data = await reader.next()
    extension = data.filename.split(".").pop().replace("/", "")
    name = ('%032x' % uuid.uuid4().int)[:8] + "." + extension
    pth = pathlib.Path(f"/var/www/idevision/tmp/{name}")
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
    print(response)
    os.remove(pth)
    return web.json_response({"data": response})
