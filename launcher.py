import asyncio
import aiohttp
import datetime
import aiohttp_jinja2
import jinja2
import os
import sys
import subprocess
import markdown2
import setproctitle
import logging
import json
from aiohttp import web

if "--close" in sys.argv:
    with open("config.json") as f:
        data = json.load(f)
    c = aiohttp.ClientSession()
    asyncio.get_event_loop().run_until_complete(c.post(f"http://127.0.0.1:{data['port']}/_internal/stop", data=data['slave_key']))
    asyncio.get_event_loop().run_until_complete(c.close())
    with open("backup/message.json") as f:
        json.dump({
            "message": "The service is currently restarting.",
            "status": 503
        }, f)

    sys.exit(0)

logger = logging.getLogger("site")
logger.setLevel(10)
handle = logging.StreamHandler(sys.stderr)
handle.setFormatter(logging.Formatter("{levelname}[{name}] : {message}", style="{"))
logger.addHandler(handle)

try:
    logger.warning("Pulling rtfs repos")
    dirs = os.listdir("repos")
    for d in dirs:
        subprocess.run(["/bin/bash", "-c", f"cd repos/{d} && git pull"])
except:
    logger.warning("Failed to pull repos")
else:
    logger.warning("Pulled repos")

try:
    import uvloop
    uvloop.install()
except:
    logger.warning("Failed to use uvloop")

import endpoints
from utils import app as _app, handler

setproctitle.setproctitle("Idevision site - Master")
uptime = datetime.datetime.utcnow()

app = _app.App()
endpoints.setup(app)
router = web.RouteTableDef()

@router.post("/api/files")
@handler.ratelimit(5, 20)
async def usercontent_upload(request: _app.TypedRequest, conn):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], "administrator" in request.user['permissions']


    if not os.path.exists(f"/var/www/idevision/containers/{auth}"):
        os.makedirs(f"/var/www/idevision/containers/{auth}")

    if "multipart" in request.content_type:
        d = await request.multipart()
        data = await d.next()
        filename = data.filename
        if "/" in filename:
            return web.Response(text="400 Bad filename", status=400)

        pth = os.path.join("/var/www/idevision/containers", auth, filename)
        with open(pth, "wb") as f:
            while True:
                chunk = await data.read_chunk()
                if not chunk:
                    break
                f.write(chunk)
    else:
        filename = request.headers.get("File-Name", None)
        if not filename:
            return web.Response(text="400 Missing File-Name header, and no multipart filename available", status=400)

        if "/" in filename:
            return web.Response(text="400 Bad filename", status=400)

        pth = os.path.join("/var/www/idevision/containers", auth, filename)
        with open(pth, "wb") as f:
            while True:
                data = await request.content.read(128)
                if not data:
                    break

                f.write(data)

    return web.json_response({"url": f"https://container.idevision.net/{auth}/{filename}"}, status=200)


@router.post("/_internal/stop")
async def stop(request: web.Request):
    if request.remote != "127.0.0.1":
        return web.Response(status=401)

    if await request.text() != app.settings['slave_key']:
        return web.Response(status=401)

    app.stop()

@router.get("/")
async def home(_):
    return web.FileResponse("static/index.html")

logger.warning("Building docs...")
with open("static/docs.md") as f:
    docs = markdown2.markdown(f.read(), extras=['fenced-code-blocks', 'break-on-newline'])
with open("static/docs.html") as f:
    docs = f.read().replace("{{docs}}", docs)

logger.warning("Built docs.")

@router.get("/docs")
async def _docs(_):
    return web.Response(text=docs, content_type="text/html")

@router.get("/newdocs")
async def _newdocs(_):
    raise web.HTTPTemporaryRedirect("/static/redoc.html")

@router.get("/robots.txt")
async def robots(_):
    return web.FileResponse("static/robots.txt")

@router.get("/favicon.ico")
async def favicon(_):
    return web.FileResponse("static/favicon.ico")

logger.debug("Mounting static routes")
router.static("/vendor", "static/vendor")
router.static("/images", "static/images")
router.static("/fonts", "static/fonts")
router.static("/css", "static/css")
router.static("/js", "static/js")
router.static("/static", "static")

aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('./'))
app.add_routes(router)

if __name__ == "__main__":
    web.run_app(
        app,
        host="127.0.0.1",
        port=app.settings['port']
    )
