import random
import datetime
import aiohttp
import os
import time
import json
import yarl

from aiohttp import web

import utils

router = web.RouteTableDef()

@router.post("/api/media/post")
async def post_media(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/media/post"):
        return web.Response(text="401 Unauthorized", status=401)

    allowed_auths = request.query.getall("authorized", None)

    t = time.time()
    options = {x: y for x, y in request.app.slaves.items() if t-y['signin'] < 300}
    if not options:
        raise ValueError("Error: no nodes available")

    target = random.choice(list(options.keys()))
    target = options[target]
    url = yarl.URL(f"http://{target['ip']}").with_port(target['port']).with_path("create")
    # use http to directly access the backend, cuz it probably isnt behind nginx

    async with aiohttp.ClientSession() as session: # cant use a global session because that would limit us to one at a time
        # also i cant be asked to make a clientsession pool
        async with session.post(url, data=request.content,
                                headers={
                                    "Authorization": request.app.settings['slave_key'],
                                    "Content-Type": request.headers.get("Content-Type")
                                }) as resp:
            if resp.status == 600:
                return web.Response(status=400, text=await resp.text())
            elif 100 >= resp.status >= 300:
                return web.Response(status=500, text=await resp.text())
            else:
                data = await resp.text()
                print(data)
                data = json.loads(data)
                new_name = data['name']
                path = data['path']
                node = data['node']

    await request.app.db.execute(
        "INSERT INTO uploads VALUES ($1,$2,$3,$4,$5,$6)",
        new_name, auth, datetime.datetime.utcnow(), node, allowed_auths, path
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
