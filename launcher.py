from aiohttp import web
import io
import random
import aiosqlite
import datetime

uptime = datetime.datetime.utcnow()

choices = list("qwertyuiopadfghjklzxcvbnmQWERTYUIOPASDFGHJKLZXCVBNM1234567890")

class App(web.Application):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_upload = None
        self.bot_stats = {
            "bob": None,
            "charles": None,
            "life": None,
            "grant": None
        }
        self.db = aiosqlite.Database("storage/data.db")

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
    for bot, values in app.bot_stats:
        response[bot] = resp = {}
        if not values:
            resp['ping'] = 0.0
            resp['status'] = "unknown"
            resp['latency'] = 0.0
        else:
            resp['ping'] = values['ping']
            resp['latency'] = values['latency']
            if datetime.datetime.utcnow().timestamp() - resp['timestamp'] > 5000:
                resp['status'] = "offline"
            else:
                resp['status'] = "online"

    return web.json_response(response, status=200)

@router.post("/api/bots/updates")
async def post_bot_stats(request: web.Request):
    auth = await get_authorization(request.headers.get("Authorization"))
    if auth not in ["bob", "grant", "life", "charles"]:
        return web.Response(status=403, text="403 UNAUTHORIZED")

    data = await request.json()
    await app.db.execute("INSERT INTO bot_stats VALUES (?,?,?,?)", auth, data['ping'], data['latency'], datetime.datetime.utcnow().timestamp())
    app.bot_stats[auth] = {"ping": data['ping'], "latency": data['ping'], "timestamp": datetime.datetime.utcnow().timestamp()}


@router.get("/")
async def home(request: web.Request):
    return web.Response(text="Soontm")

app.add_routes(router)
web.run_app(
    app,
    host="127.0.0.1",
    port=8333
)