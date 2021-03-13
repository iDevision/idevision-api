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

@router.get("/api/bots/stats")
async def get_bot_stats(_):
    response = {}
    for bot, d in app.bot_stats.items():
        response[bot] = {
            "metrics": d['metrics'],
            "ramusage": d['ram_usage'],
            "online": d['online'],
            "usercount": d['user_count'],
            "guildcount": d['guild_count'],
            "latency": d['latency'],
            "updated_at": d['last_post'].timestamp()
        }

    return web.json_response(response, status=200)

@router.get("/metrics")
async def get_metrics(_):
    data = prometheus_client.generate_latest()
    resp = web.Response(body=data, headers={"Content-type": prometheus_client.CONTENT_TYPE_LATEST})
    return resp

@router.post("/api/bots/updates")
async def post_bot_stats(request: utils.TypedRequest):
    payload = {
        "metrics": {
            "GUILD_CREATE": 0,
            "MESSAGE_CREATE": 0 # etc
        },
        "usercount": 0,
        "guildcount": 0,
        "ramusage": 300, # in mb
        "latency": 99 # in ms
    }
    token = request.headers.get("Authorization")
    auth, _ = await utils.get_authorization(request, token)
    if not auth or not token.startswith("bot."):
        return web.Response(status=401, text="401 Unauthorized")

    data = await request.json()

    app.bot_stats[auth] = {
        "last_post": datetime.datetime.utcnow(),
        "metrics": {x: 0 for x in metrics},
        "ram_usage": data.get("ramusage", 0),
        "latency": data.get("latency", 0),
        "online": True,
        "user_count": data.get("usercount", 0),
        "guild_count": data.get("guildcount", 0)
        }

    for metric, val in data['metrics'].items():
        app.prometheus['websocket_events'].labels(event=metric, bot=auth).inc(
            max(val - app.prometheus['websocket_events'].labels(event=metric, bot=auth)._value.get(), 0)) # noqa

    d = app.prometheus
    d["counts"].labels(count="users", bot=auth).set(data['usercount'])
    d['counts'].labels(count="guilds", bot=auth).set(data['guildcount'])
    d['online'].labels(bot=auth).info({"state": "Online"})
    d['latency'].labels(count="latency", bot=auth).set(data['latency'])
    d['ram_usage'].labels(count="ram", bot=auth).set(data['ramusage'])

    return web.Response(status=204)


@router.post("/api/git/checks")
async def git_checks(request: utils.TypedRequest):
    data = await request.json()

    if data['action'] == "completed" and data['check_run']['conclusion'] == "success":
        import subprocess
        subprocess.run(["/usr/bin/git", "pull", "origin", "master"])
        print(f"restart from {request.headers['x-forwarded-ip']}", file=sys.stderr)
        request.app.stop()

    return web.Response()

@router.post("/api/home/urls")
async def home_urls(request: utils.TypedRequest):
    auth, _ = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    user = data['user']
    displayname = data['display_name']

    link1 = data['link1'], data['link1_name']
    link2 = data['link2'], data['link2_name']
    link3 = data['link3'], data['link3_name']
    link4 = data['link4'], data['link4_name']

    await app.db.execute("""INSERT INTO homepages VALUES ($1, $10, $2, $3, $4, $5, $6, $7, $8, $9)
    ON CONFLICT (username) DO UPDATE SET 
    display_name = $10,
    link1 = $2, link1_name = $3,
    link2 = $4, link2_name = $5,
    link3 = $6, link3_name = $7,
    link4 = $8, link4_name = $9
    """, user, *link1, *link2, *link3, *link4, displayname)

    return web.Response(status=204)

@router.get("/homepage")
@aiohttp_jinja2.template("homepage.html")
async def home(request: web.Request):
    usr = request.query.get("user", "Unknown")
    row = await app.db.fetchrow("SELECT * FROM homepages WHERE username = $1", usr)
    if not row:
        return {
            "name": "Unknown",
            "link1": "https://duckduckgo.com",
            "link2": "https://duckduckgo.com",
            "link3": "https://duckduckgo.com",
            "link4": "https://duckduckgo.com",
            "link1name": "DuckDuckGo",
            "link2name": "DuckDuckGo",
            "link3name": "DuckDuckGo",
            "link4name": "DuckDuckGo",
        }

    return {
        "name": row['display_name'],
        "link1": row['link1'],
        "link2": row['link2'],
        "link3": row['link3'],
        "link4": row['link4'],
        "link1name": row['link1_name'],
        "link2name": row['link2_name'],
        "link3name": row['link3_name'],
        "link4name": row['link4_name'],
    }

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
