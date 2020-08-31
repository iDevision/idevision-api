from aiohttp import web
import io
import random
import asyncpg
import datetime
import prometheus_client
import asyncio
import os
import sys

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
        self.bot_stats = {
            "bob": {
                "counts": prometheus_client.Gauge("bob_data", "Guilds that BOB has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("bob_events", "BOB's metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("bob_latency", "BOB's latency", labelnames=["count"]),
                "ram_usage": prometheus_client.Gauge("bob_ram", "How much ram BOB is using", labelnames=["count"]),
                "online": prometheus_client.Info("bob_online", "BOB's status"),
                "last_post": None,
                "raw_metrics": {x: 0 for x in metrics}
            },
            "bobbeta": {
                "counts": prometheus_client.Gauge("bob_beta_data", "Guilds that BOB has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("bob_beta_events", "BOB's metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("bob_beta_latency", "BOB's latency", labelnames=["count"]),
                "ram_usage": prometheus_client.Gauge("bob_beta_ram", "How much ram BOB is using", labelnames=["count"]),
                "online": prometheus_client.Info("bob_beta_online", "BOB's status"),
                "last_post": None,
                "raw_metrics": {x: 0 for x in metrics}
            },
            "charles": {
                "counts": prometheus_client.Gauge("charles_data", "Guilds that Charles has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("charles_events", "Charles' metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("charles_latency", "Charles' latency", labelnames=["count"]),
                "ram_usage": prometheus_client.Gauge("charles_ram", "How much ram Charles is using", labelnames=["count"]),
                "online": prometheus_client.Info("charles_online", "Charles' status"),
                "last_post": None,
                "raw_metrics": {x: 0 for x in metrics}
            },
            "life": {
                "counts": prometheus_client.Gauge("life_data", "Guilds that Life has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("life_events", "Life's metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("life_latency", "Life's latency", labelnames=["count"]),
                "ram_usage": prometheus_client.Gauge("life_ram", "How much ram Life is using", labelnames=["count"]),
                "online": prometheus_client.Info("life_online", "Life's status"),
                "last_post": None,
                "raw_metrics": {x: 0 for x in metrics}
            },
            #"grant": None
        }
        self.on_startup.append(self.async_init)

    async def async_init(self, _):
        if test:
            pass
        else:
            self.db = await asyncpg.create_pool("postgresql://tom:tom@207.244.228.96:5432/idevision")

    async def offline_task(self):
        while True:
            for bot in self.bot_stats.values():
                if bot['last_post'] is None or (datetime.datetime.utcnow() - bot['last_post']).total_seconds() > 120:
                    bot['online'].info({"state": "Offline"})

                await asyncio.sleep(120)

app = App()
router = web.RouteTableDef()

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
    new_name = "".join([random.choice(choices) for _ in range(3)]) + f".{extension}"
    buffer = io.FileIO(f"/var/www/idevision/media/{new_name}", mode="w")
    while True:
        chunk = await data.read_chunk()
        if not chunk:
            break
        buffer.write(chunk)

    buffer.close()
    await app.db.execute("INSERT INTO uploads VALUES ($1,$2,$3)", new_name, auth, datetime.datetime.utcnow())
    app.last_upload = new_name
    return web.json_response({"url": "https://cdn.idevision.net/"+new_name}, status=200)

@router.delete("/api/media/images/{image}")
async def delete_image(request: web.Request):
    auth, routes = await get_authorization(request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not route_allowed(routes, "api/media/images"):
        return web.Response(text="401 Unauthorized", status=401)

    if test:
        return web.Response(status=204)

    if not await app.db.fetchrow("DELETE FROM uploads WHERE key = $1 AND username = $2 RETURNING *;", request.match_info.get("image")):
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
    for bot in ["bob", "bobbeta", "charles", "life"]:
        d = app.bot_stats[bot]
        response[bot] = {
            "metrics": d['raw_metrics'],
            "ramusage": d['ram_usage'].labels(count="ram")._value.get() or None,
            "online": d['online']._value.get("state", "Offline") == "Online",
            "usercount": d['counts'].labels(count="users")._value._value or None,
            "guildcount": d['counts'].labels(count="guilds")._value._value or None,
            "latency": d['latency'].labels(count="latency")._value._value or None,
            "updated_at": d['last_post'].timestamp() if d['last_post'] is not None else None
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
    auth, _ = await get_authorization(request.headers.get("Authorization"))
    if auth not in ["bob", "bobbeta", "life", "charles"]:
        return web.Response(status=401, text="401 Unauthorized")

    data = await request.json()
    app.bot_stats[auth]['raw_metrics'] = data['metrics']

    for metric, val in data['metrics'].items():
        app.bot_stats[auth]['websocket_events'].labels(event=metric).inc(max(val - app.bot_stats[auth]['websocket_events'].labels(event=metric)._value.get(), 0))

    d = app.bot_stats[auth]
    d["counts"].labels(count="users").set(data['usercount'])
    d['counts'].labels(count="guilds").set(data['guildcount'])
    d['last_post'] = datetime.datetime.utcnow()
    d['online'].info({"state": "Online"})
    d['latency'].labels(count="latency").set(data['latency'])
    d['ram_usage'].labels(count="ram").set(data['ramusage'])
    return web.Response()


@router.post("/api/git/checks")
async def git_checks(request: web.Request):
    data = await request.json()

    if data['action'] == "completed" and data['check_run']['conclusion'] == "success":
        import subprocess
        v = subprocess.run(["/usr/bin/bash", "-c 'at now'"], input=b"git pull origin master && systemctl restart idevision")
        print("restarting...")

    return web.Response()

@router.get("/")
async def home(request: web.Request):
    return web.Response(body=index, content_type="text/html")


router.static("/vendor", "vendor")
router.static("/images", "images")
router.static("/fonts", "fonts")
router.static("/css", "css")

with open("index.html") as f:
    index = f.read()

app.add_routes(router)

if __name__ == "__main__":
    web.run_app(
        app,
        host="127.0.0.1",
        port=8333
    )
