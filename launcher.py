from aiohttp import web
import datetime
import prometheus_client
import aiohttp_jinja2
import jinja2
import os
import sys
import subprocess

subprocess.run(["/bin/bash", "-c", "pip install -U -r requirements.txt"], stderr=sys.stderr, stdout=sys.stdout) # update these manually, just to make sure the rtfs is up to date

import endpoints
import utils

uptime = datetime.datetime.utcnow()
test = "--unittest" in sys.argv

choices = list("qwertyuiopadfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM1234567890")
metrics = [
    "PRESENCE_UPDATE",
    "MESSAGE_CREATE",
    "TYPING_START",
    "GUILD_MEMBER_UPDATE",
    "MESSAGE_UPDATE",
    "MESSAGE_REACTION_ADD",
    "MESSAGE_REACTION_REMOVE",
    "VOICE_STATE_UPDATE",
    "GUILD_MEMBER_ADD",
    "GUILD_MEMBERS_CHUNK",
    "MESSAGE_DELETE",
    "GUILD_MEMBER_REMOVE",
    "GUILD_CREATE",
    "MESSAGE_REACTION_REMOVE_ALL",
    "READY",
    "VOICE_SERVER_UPDATE",
    "RESUMED"
]
DEFAULT_ROUTES = [
    "api/media/post",
    "api/media/stats/image",
    "api/media/stats/user",
    "api/media/list",
    "api/media/list/user",
    "api/media/images",
]

app = utils.App()
endpoints.setup(app)
router = web.RouteTableDef()

router.static("/static", "./static")

@router.get("/docs")
async def _docs(_):
    raise web.HTTPPermanentRedirect("/static/docs.html")

@router.post("/api/media/container/upload")
async def usercontent_upload(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/container"):
        return web.Response(text="401 Unauthorized", status=401)

    if test:
        return web.Response(status=204)

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
                data = await request.content.read(120)
                if not data:
                    break

                f.write(data)

    return web.json_response({"url": f"https://container.idevision.net/{auth}/{filename}"}, status=200)


@router.post("/api/git/checks")
async def git_checks(request: utils.TypedRequest):
    data = await request.json()

    if data['action'] == "completed" and data['check_run']['conclusion'] == "success":
        import subprocess
        subprocess.run(["/usr/bin/git", "pull", "origin", "master"])
        print(f"restart from {request.headers['x-forwarded-ip']}", file=sys.stderr)
        request.app.stop()

    return web.Response()

@router.get("/")
async def home(_):
    return web.FileResponse("index.html")

@router.get("/robots.txt")
async def robots(_):
    return web.FileResponse("static/robots.txt")

@router.get("/favicon.ico")
async def favicon(_):
    return web.FileResponse("static/favicon.ico")

router.static("/vendor", "vendor")
router.static("/images", "images")
router.static("/fonts", "fonts")
router.static("/css", "css")
router.static("/js", "js")

aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('./'))
app.add_routes(router)

if __name__ == "__main__":
    web.run_app(
        app,
        host="127.0.0.1",
        port=8340
    )
