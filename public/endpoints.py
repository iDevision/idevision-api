from yarl import URL
from aiohttp import web

from .ratelimit import ratelimit
from .rtfm import DocReader
from .rtfs import Index

import twitchio, discord

print("[RTFS] Start indexing")
rtfs_cache = {
    "discord.py": Index(f"https://github.com/Rapptz/discord.py/blob/v{discord.__version__.strip('a')}/").do_index(discord, 1, 2),
    "twitchio": Index(f"https://github.com/TwitchIO/TwitchIO/blob/v{twitchio.__version__.strip('a')}/").do_index(twitchio, 2, 2)
}
print("[RTFS] Finish indexing")

reader = DocReader()

router = web.RouteTableDef()

@router.get("/api/public/rtfs")
@ratelimit(2, 10)
async def do_rtfs(request: web.Request):
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
@ratelimit(2, 10)
async def do_rtfm(request: web.Request):
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

