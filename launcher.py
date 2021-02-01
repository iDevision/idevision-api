from aiohttp import web
import io
import random
import asyncpg
import datetime
import prometheus_client
import aiohttp_jinja2
import jinja2
import asyncio
import os
import sys
import subprocess

subprocess.run(["/bin/bash", "-c", "pip install -U -r requirements.txt"], stderr=sys.stderr, stdout=sys.stdout) # update these manually, just to make sure the rtfs is up to date

from public.endpoints import router as _api_router

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

class App(web.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_upload = None
        self.prometheus = {
            "counts": prometheus_client.Gauge("bot_data", "Guilds that the bot has", labelnames=["count", "bot"]),
            "websocket_events": prometheus_client.Counter("bot_events", "bot's metrics", labelnames=['event', "bot"]),
            "latency": prometheus_client.Gauge("bot_latency", "bot's latency", labelnames=["count", "bot"]),
            "ram_usage": prometheus_client.Gauge("bot_ram", "How much ram the bot is using", labelnames=["count", "bot"]),
            "online": prometheus_client.Info("bot_online", "the bot's status", labelnames=["bot"]),
        }
        self.bot_stats = {}
        self.on_startup.append(self.async_init)

    async def async_init(self, _):
        if test:
            pass
        else:
            self.db = await asyncpg.create_pool("postgresql://tom:tom@127.0.0.1:5432/idevision")

    async def offline_task(self):
        while True:
            for bname, bot in self.bot_stats.items():
                if bot['last_post'] is None or (datetime.datetime.utcnow() - bot['last_post']).total_seconds() > 120:
                    self.prometheus['online'].labels(bot=bname).info({"state": "Offline"})

                await asyncio.sleep(120)

app = App()
app.add_routes(_api_router)
router = web.RouteTableDef()

router.static("/static", "./static")

@router.get("/docs")
async def _docs(req):
    raise web.HTTPPermanentRedirect("/static/docs.txt")

async def get_authorization(authorization):
    if test:
        return "iamtomahawkx", ["*"]

    resp = await app.db.fetchrow("SELECT username, allowed_routes FROM auths WHERE auth_key = $1 and active = true", authorization)
    if resp is not None:
        return resp['username'], resp['allowed_routes']
    return None, []

def route_allowed(allowed_routes, route):
    if "*" in allowed_routes:
        return True

    if "{" in route:
        route = route.split("{")[0] # remove any args

    route = route.strip("/")
    return route in allowed_routes

@router.post("/api/media/post")
async def post_media(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/post"):
        return web.Response(text="401 Unauthorized", status=401)

    reader = await request.multipart()
    data = await reader.next()
    extension = data.filename.split(".").pop()
    new_name = "".join([random.choice(choices) for _ in range(8)]) + f".{extension}"
    buffer = io.FileIO(f"/var/www/idevision/media/{new_name}", mode="w")
    while True:
        chunk = await data.read_chunk()
        if not chunk:
            break
        buffer.write(chunk)

    buffer.close()
    await app.db.execute("INSERT INTO uploads VALUES ($1,$2,$3)", new_name, auth, datetime.datetime.utcnow())
    app.last_upload = new_name
    if auth == "random" or auth == "life":
        return web.json_response({"url": "https://cdn.idevision.net/tLu.png", "sike_heres_the_real_url": "https://cdn.idevision.net/"+new_name})

    return web.json_response({"url": "https://cdn.idevision.net/"+new_name}, status=200)

@router.post("/api/media/container/upload")
async def usercontent_upload(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/container"):
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


@router.delete("/api/media/images/{image}")
async def delete_image(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/images"):
        return web.Response(text="401 Unauthorized", status=401)

    if test:
        return web.Response(status=204)

    if "*" in routes:
        coro = app.db.fetchrow("DELETE FROM uploads WHERE key = $1 RETURNING *;", request.match_info.get("image"))

    else:
        coro = app.db.fetchrow("DELETE FROM uploads WHERE key = $1 AND username = $2 RETURNING *;", request.match_info.get("image"), auth)

    if not await coro:
        if "*" in routes:
            return web.Response(text="404 NOT FOUND", status=404)

        return web.Response(text="401 Unauthorized", status=401)

    os.remove("/var/www/idevision/media/"+request.match_info.get("image"))
    return web.Response(status=204)

@router.delete("/api/media/purge")
async def purge_user(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/purge"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if test:
        return web.Response(status=204)

    data = await app.db.fetch("DELETE FROM uploads WHERE username = $1 RETURNING *;", usr)
    if not data:
        return web.Response(status=400, reason="User not found/no images to delete")

    for row in data:
        os.remove("/var/www/idevision/media/" + row['key'])

    return web.Response()

@router.get("/api/media/stats")
async def get_media_stats(request: web.Request):
    if test:
        amount = 10
    else:
        amount = await app.db.fetchval("SELECT COUNT(*) FROM uploads;")

    return web.json_response({
        "upload_count": amount,
        "last_upload": app.last_upload
    })

@router.get("/api/media/list")
async def get_media_list(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/list"):
        return web.Response(text="401 Unauthorized", status=401)

    if test:
        return web.json_response({"iamtomahawkx": ["1.png", "2.png"]})

    values = await app.db.fetch("SELECT * FROM uploads")
    resp = {}
    for rec in values:
        if rec['username'] in resp:
            resp[rec['username']].append(rec['key'])
        else:
            resp[rec['username']] = [rec['key']]

    return web.json_response(resp)

@router.get("/api/media/list/user/{user}")
async def get_media_list(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/list/user"):
        return web.Response(text="401 Unauthorized", status=401)

    usr = request.match_info.get("user", auth)
    if test:
        return web.json_response(["1.png", "2.jpg"])

    values = await app.db.fetch("SELECT * FROM uploads WHERE username = $1;", usr)
    return web.json_response([rec['key'] for rec in values])

@router.get("/api/media/images/{image}")
async def get_upload_stats(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/images"):
        return web.Response(text="401 Unauthorized", status=401)

    key = request.match_info.get("key")
    if test:
        return web.json_response({
            "url": "https://cdn.idevision.net/abc.png",
            "timestamp": datetime.datetime.utcnow().timestamp(),
            "username": "iamtomahawkx"
        })

    about = await app.db.fetchrow("SELECT * FROM uploads WHERE key = $1", key)
    if not about:
        return web.Response(text="404 Not Found", status=404)

    return web.json_response({
        "url": "https://cdn.idevision.net/" + about[0],
        "timestamp": about[2].timestamp(),
        "username": about[1]
    })

@router.get("/api/media/stats/user")
async def get_user_stats(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/stats/user"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    if test:
        return web.json_response({
            "upload_count": 0,
            "last_upload": "https://cdn.idevision.net/abc.png"
        })

    amount = await app.db.fetchval("SELECT COUNT(*) FROM uploads WHERE username = $1", data['username'])
    recent = await app.db.fetchval("SELECT key FROM uploads WHERE username = $1 ORDER BY time DESC", data['username'])
    if not amount and not recent:
        return web.Response(status=400, reason="User not found/no entries")

    return web.json_response({
        "upload_count": amount,
        "last_upload": "https://cdn.idevision.net/" + recent
    })

@router.post("/api/users/manage")
async def add_user(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    routes = [x.strip("/") for x in data.get("routes", [])] or DEFAULT_ROUTES
    if test:
        return web.Response(status=204)

    await app.db.execute("INSERT INTO auths VALUES ($1, $2, $3, true)", data['username'], data['authorization'], routes)
    return web.Response(status=204)

@router.delete("/api/users/manage")
async def remove_user(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if test:
        return web.Response(status=204)

    data = await app.db.fetch("SELECT key FROM uploads WHERE username = $1", usr)
    for row in data:
        os.remove("/var/www/idevision/media/" + row['key'])

    await app.db.execute("DELETE FROM auths WHERE username = $1", usr)
    return web.Response(status=204)

@router.post("/api/users/deauth")
async def deauth_user(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")

    if test:
        return web.Response(status=204)

    await app.db.fetchrow("UPDATE auths SET active = false WHERE username = $1", usr)
    return web.Response(status=204)

@router.post("/api/users/auth")
async def auth_user(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if test:
        return web.Response(status=204)

    await app.db.fetchrow("UPDATE auths SET active = true WHERE username = $1", usr)
    return web.Response(status=204)

@router.get("/api/bots/stats")
async def get_bot_stats(request: web.Request):
    response = {}
    for bot, d in app.bot_stats.items():
        print(d)
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
async def get_metrics(request: web.Request):
    data = prometheus_client.generate_latest()
    resp = web.Response(body=data, headers={"Content-type": prometheus_client.CONTENT_TYPE_LATEST})
    return resp

@router.post("/api/bots/updates")
async def post_bot_stats(request: web.Request):
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
    auth, _ = await get_authorization(token)
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
async def git_checks(request: web.Request):
    data = await request.json()

    if data['action'] == "completed" and data['check_run']['conclusion'] == "success":
        import subprocess
        subprocess.run(["/usr/bin/bash", "-c", "at now"], input=b"git pull origin master && systemctl --user restart idevision")
        print(f"restart from {request.headers['x-real-ip']}", file=sys.stderr)

    return web.Response()

@router.post("/api/home/urls")
async def home_urls(request: web.Request):
    auth, _ = await get_authorization(request.headers.get("Authorization"))
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
async def home(request: web.Request):
    return web.Response(body=index, content_type="text/html")


router.static("/vendor", "vendor")
router.static("/images", "images")
router.static("/fonts", "fonts")
router.static("/css", "css")
router.static("/js", "js")

with open("index.html") as f:
    index = f.read()

with open("homepage.html") as f:
    homepage = f.read()

aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('./'))
app.add_routes(router)

if __name__ == "__main__":
    web.run_app(
        app,
        host="127.0.0.1",
        port=8333
    )
