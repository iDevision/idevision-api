import random
import io
import datetime
import string
import mimetypes
import os

from aiohttp import web

import utils

router = web.RouteTableDef()
CHOICES = string.digits + string.ascii_letters

@router.post("/api/media/post")
async def post_media(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/post"):
        return web.Response(text="401 Unauthorized", status=401)

    reader = await request.multipart()
    data = await reader.next()
    extension = mimetypes.guess_extension(data.filename)
    new_name = "".join([random.choice(CHOICES) for _ in range(8)]) + extension
    buffer = io.FileIO(f"/var/www/idevision/media/{new_name}", mode="w")
    allowed_auths = request.query.getall("authorization", None)

    while True:
        chunk = await data.read_chunk()
        if not chunk:
            break
        buffer.write(chunk)

    buffer.close()
    await request.app.db.execute(
        "INSERT INTO uploads VALUES ($1,$2,$3,0,$4,$5)",
        new_name, auth, datetime.datetime.utcnow(), allowed_auths, f"/var/www/idevision/media/{new_name}"
    )
    request.app.last_upload = new_name

    return web.json_response({"url": "https://cdn.idevision.net/"+new_name}, status=200)

@router.delete("/api/media/images/{image}")
async def delete_image(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/images"):
        return web.Response(text="401 Unauthorized", status=401)

    if request.app.test:
        return web.Response(status=204)

    if "*" in routes:
        coro = request.app.db.fetchrow("DELETE FROM uploads WHERE key = $1 RETURNING *;", request.match_info.get("image"))

    else:
        coro = request.app.db.fetchrow("DELETE FROM uploads WHERE key = $1 AND username = $2 RETURNING *;", request.match_info.get("image"), auth)

    if not await coro:
        if "*" in routes:
            return web.Response(status=404)

        return web.Response(status=401, text="401 Unauthorized")

    os.remove("/var/www/idevision/media/"+request.match_info.get("image"))
    return web.Response(status=204)

@router.delete("/api/media/purge")
async def purge_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/purge"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if request.app.test:
        return web.Response(status=204)

    data = await request.app.db.fetch("DELETE FROM uploads WHERE username = $1 RETURNING *;", usr)
    if not data:
        return web.Response(status=400, reason="User not found/no images to delete")

    for row in data:
        os.remove("/var/www/idevision/media/" + row['key'])

    return web.Response()

@router.get("/api/media/stats")
async def get_media_stats(request: utils.TypedRequest):
    if request.app.test:
        amount = 10
    else:
        amount = await request.app.db.fetchval("SELECT COUNT(*) FROM uploads;")

    return web.json_response({
        "upload_count": amount,
        "last_upload": request.app.last_upload
    })

@router.get("/api/media/list")
async def get_media_list(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/list"):
        return web.Response(text="401 Unauthorized", status=401)

    if request.app.test:
        return web.json_response({"iamtomahawkx": ["1.png", "2.png"]})

    values = await request.app.db.fetch("SELECT * FROM uploads")
    resp = {}
    for rec in values:
        if rec['username'] in resp:
            resp[rec['username']].append(rec['key'])
        else:
            resp[rec['username']] = [rec['key']]

    return web.json_response(resp)

@router.get("/api/media/images/{image}")
async def get_upload_stats(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/images"):
        return web.Response(text="401 Unauthorized", status=401)

    key = request.match_info.get("key")
    if request.app.test:
        return web.json_response({
            "url": "https://cdn.idevision.net/abc.png",
            "timestamp": datetime.datetime.utcnow().timestamp(),
            "username": "iamtomahawkx"
        })

    about = await request.app.db.fetchrow("SELECT * FROM uploads WHERE key = $1", key)
    if not about:
        return web.Response(status=404)

    return web.json_response({
        "url": "https://cdn.idevision.net/" + about[0],
        "timestamp": about[2].timestamp(),
        "username": about[1]
    })

@router.get("/api/media/stats/user")
async def get_user_stats(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/stats/user"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    if request.app.test:
        return web.json_response({
            "upload_count": 0,
            "last_upload": "https://cdn.idevision.net/abc.png"
        })

    amount = await request.app.db.fetchval("SELECT COUNT(*) FROM uploads WHERE username = $1", data['username'])
    recent = await request.app.db.fetchval("SELECT key FROM uploads WHERE username = $1 ORDER BY time DESC", data['username'])
    if not amount and not recent:
        return web.Response(status=400, reason="User not found/no entries")

    return web.json_response({
        "upload_count": amount,
        "last_upload": "https://cdn.idevision.net/" + recent
    })

@router.get("/api/media/list/user/{user}")
async def get_media_list(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/list/user"):
        return web.Response(text="401 Unauthorized", status=401)

    usr = request.match_info.get("user", auth)
    if request.app.test:
        return web.json_response(["1.png", "2.jpg"])

    values = await request.app.db.fetch("SELECT * FROM uploads WHERE username = $1;", usr)
    return web.json_response([rec['key'] for rec in values])
