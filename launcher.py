from aiohttp import web
import io
import random
import aiosqlite
import datetime
import prometheus_client
import asyncio

uptime = datetime.datetime.utcnow()

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

class App(web.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_upload = None
        self.bot_stats = {
            "bob": {
                "counts": prometheus_client.Gauge("bob_data", "Guilds that BOB has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("bob_events", "BOB's metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("bob_latency", "BOB's latency"),
                "ram_usage": prometheus_client.Gauge("bob_ram", "How much ram BOB is using"),
                "online": prometheus_client.Enum("bob_online", "BOB's status", states=["online", "offline"]),
                "last_post": None
            },
            "bobbeta": {
                "counts": prometheus_client.Gauge("bob_beta_data", "Guilds that BOB has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("bob_beta_events", "BOB's metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("bob_beta_latency", "BOB's latency", labelnames=["count"]),
                "ram_usage": prometheus_client.Gauge("bob_beta_ram", "How much ram BOB is using"),
                "online": prometheus_client.Enum("bob_beta_online", "BOB's status", states=["online", "offline"]),
                "last_post": None
            },
            "charles": {
                "counts": prometheus_client.Gauge("charles_data", "Guilds that Charles has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("charles_events", "Charles' metrics", labelnames=['event']),
                "latency": prometheus_client.Gauge("charles_latency", "Charles' latency"),
                "ram_usage": prometheus_client.Gauge("charles_ram", "How much ram Charles is using"),
                "online": prometheus_client.Enum("charles_online", "Charles' status", states=["online", "offline"]),
                "last_post": None
            },
            "life": {
                "counts": prometheus_client.Gauge("life_data", "Guilds that Life has", labelnames=["count"]),
                "websocket_events": prometheus_client.Counter("life_events", "Life's metrics", labelnames=['events']),
                "latency": prometheus_client.Gauge("life_latency", "Life's latency"),
                "ram_usage": prometheus_client.Gauge("life_ram", "How much ram Life is using"),
                "online": prometheus_client.Enum("life_online", "Life's status", states=["online", "offline"]),
                "last_post": None
            },
            #"grant": None
        }
        self.db = aiosqlite.Database("storage/data.db")

    async def offline_task(self):
        while True:
            for bot in self.bot_stats.values():
                if bot['last_post'] is None or (datetime.datetime.utcnow() - bot['last_post']).total_seconds() > 120:
                    bot['online'].set('offline')

                await asyncio.sleep(120)

app = App()
router = web.RouteTableDef()

async def get_authorization(authorization):
    await app.db.execute("INSERT OR IGNORE INTO auths VALUES (?,?)", "tom", "Welcomer Sucks")
    if authorization is None:
        return None

    resp = await app.db.fetchrow("SELECT username FROM auths WHERE authorization = ?", authorization)
    if resp is not None:
        return resp[0]
    return None

@router.post("/api/media/post")
async def post_media(request: web.Request):
    auth = await get_authorization(request.headers.get("Authorization"))
    if not auth:
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
    await app.db.execute("INSERT INTO uploads VALUES (?,?,?)", new_name, auth, datetime.datetime.utcnow().timestamp())
    app.last_upload = new_name
    return web.json_response({"url": "https://media.idevision.net/"+new_name}, status=200)

@router.get("/api/media/stats")
async def get_media_stats(request: web.Request):
    amount = await app.db.fetchval("SELECT COUNT(*) FROM uploads;")
    return web.json_response({
        "upload_count": amount,
        "last_upload": app.last_upload
    })

@router.get("/api/media/stats/image")
async def get_upload_stats(request: web.Request):
    try:
        data = await request.json()
        if "key" not in data:
            raise ValueError
    except:
        return web.Response(text="400 Bad Request", status=400)

    auth = await get_authorization(request.headers.get("Authorization"))
    if not auth or auth != "tom":
        return web.Response(text="401 Unauthorized", status=401)

    about = await app.db.fetchrow("SELECT * FROM uploads WHERE key = ?", data['key'])
    if not about:
        return web.Response(text="404 Not Found", status=404)

    return web.json_response({
        "url": "https://media.idevision.net/" + about[0],
        "timestamp": about[2],
        "username": about[1]
    })

@router.get("/api/media/stats/user")
async def get_user_stats(request: web.Request):
    auth = await get_authorization(request.headers.get("Authorization"))
    if not auth or auth != "tom":
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    amount = await app.db.fetchval("SELECT COUNT(*) FROM uploads WHERE user = ?", data['username'])
    recent = await app.db.fetchval("SELECT key FROM uploads WHERE user = ? ORDER BY time DESC", data['username'])
    return web.json_response({
        "posts": amount,
        "most_recent": "https://media.idevision.net/" + recent
    })

@router.post("/api/users/add")
async def add_user(request: web.Request):
    auth = await get_authorization(request.headers.get("Authorization"))
    if not auth or auth != "tom":
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    await app.db.execute("INSERT INTO auths VALUES (?,?)", data['username'], data['authorization'])
    return web.Response(status=200, text="200 OK")


@router.get("/api/bots/stats")
async def get_bot_stats(request: web.Request):
    response = {}
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
    auth = await get_authorization(request.headers.get("Authorization"))
    if auth not in ["bob", "bobbeta", "life", "charles"]:
        return web.Response(status=401, text="401 Unauthorized")

    data = await request.json()

    for metric, val in data['metrics'].items():
        app.bot_stats[auth]['websocket_events'].labels(event=metric).inc(val - app.bot_stats[auth]['websocket_events'].labels(event=metric)._value.get())

    d = app.bot_stats[auth]
    d["counts"].labels(count="users").set(data['usercount'])
    d['counts'].labels(count="guilds").set(data['guildcount'])
    print(data)
    d['last_post'] = datetime.datetime.utcnow()
    d['online'].state("online")
    d['latency'].labels(count="latency").set(data['latency'])
    return web.Response()


@router.get("/")
async def home(request: web.Request):
    return web.Response(text="Soontm")

app.add_routes(router)
web.run_app(
    app,
    host="127.0.0.1",
    port=8333
)