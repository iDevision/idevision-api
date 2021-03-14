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

@router.post("/api/cdn/post")
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
                data = json.loads(data)
                new_name = data['name']
                path = data['path']
                node = data['node']

    await request.app.db.execute(
        "INSERT INTO uploads VALUES ($1,$2,$3,0,$4,$5,$6)",
        new_name, auth, datetime.datetime.utcnow(), allowed_auths, path, node
    )
    request.app.last_upload = new_name

    return web.json_response({"url": f"https://{request.app.settings['child_site']}/{node}/{new_name}", "slug": new_name, "name": new_name, "node": node}, status=200)

@router.delete("/api/cdn/images/{node}/{image}")
async def delete_image(request: utils.TypedRequest):
    node = request.match_info.get("node")
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/cdn/images"):
        return web.Response(text="401 Unauthorized", status=401)

    try:
        if int(node) not in request.app.slaves:
            return web.Response(status=400, text="Node is unavailable or does not exist")
    except:
        return web.Response(status=400, text="Expected an integer for value 'node'")

    if "*" in routes:
        coro = request.app.db.fetchrow(
            "UPDATE uploads SET deleted = true WHERE key = $1 AND node = $2 RETURNING *;",
            request.match_info.get("image"),
            node
        )

    else:
        coro = request.app.db.fetchrow(
            "UPDATE uploads SET deleted = true WHERE key = $1 AND node = $2 AND username = $3 RETURNING *;",
            request.match_info.get("image"),
            node,
            auth
        )
    if not await coro:
        if "*" in routes:
            return web.Response(status=404)

        return web.Response(status=401, text="401 Unauthorized")

    target = request.app.slaves[node]
    url = yarl.URL(f"http://{target['ip']}").with_port(target['port']).with_path("delete")

    async with aiohttp.ClientSession() as session:
        async with session.post(
                url,
                text=request.match_info.get("image"),
                headers={"Authorization": request.app.settings['slave_key']}
        ) as resp:
            return web.Response(status=resp.status)

@router.delete("/api/cdn/purge")
async def purge_user(request: utils.TypedRequest):
    return web.Response(status=501)
    # TODO

    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/cdn/purge"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if request.app.test:
        return web.Response(status=204)

    data = await request.app.db.fetch("UPDATE uploads SET deleted = true WHERE username = $1 RETURNING *;", usr)
    if not data:
        return web.Response(status=400, reason="User not found/no images to delete")

    for row in data:
        os.remove("/var/www/idevision/cdn/" + row['key'])

    return web.Response()

@router.get("/api/cdn/stats")
async def get_cdn_stats(request: utils.TypedRequest):
    amount = await request.app.db.fetchval("SELECT COUNT(*) FROM uploads WHERE deleted is false;")

    return web.json_response({
        "upload_count": amount,
        "last_upload": request.app.last_upload
    })

@router.get("/api/cdn/list")
async def get_cdn_list(request: utils.TypedRequest):
    return web.Response(status=501)
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/cdn/list"):
        return web.Response(text="401 Unauthorized", status=401)

    values = await request.app.db.fetch("SELECT key, node, username FROM uploads where deleted is false")
    resp = {}
    for rec in values:
        if rec['username'] in resp:
            resp[rec['username']].append({"key": rec['key'], "node": rec['node']})
        else:
            resp[rec['username']] = [{"key": rec['key'], "node": rec['node']}]

    return web.json_response(resp)

@router.get("/api/cdn/images/{node}/{image}")
async def get_upload_stats(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/cdn/images"):
        return web.Response(text="401 Unauthorized", status=401)

    key = request.match_info.get("key")
    try:
        node = int(request.match_info.get("node"))
    except:
        return web.Response(status=400, text="Expected an int for value 'node'")

    about = await request.app.db.fetchrow("SELECT * FROM uploads WHERE key = $1 AND node = $2 and deleted is false", key, node)
    if not about:
        return web.Response(status=404)

    return web.json_response({
        "url": f"https://{request.app.settings['child_site']}/{about['node']}/{about['key']}",
        "timestamp": about['time'].timestamp(),
        "author": about['username'],
        "views": about['views']
    })

@router.get("/api/cdn/stats/user")
async def get_user_stats(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/cdn/stats/user"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()

    amount = await request.app.db.fetchval("SELECT COUNT(*) FROM uploads WHERE username = $1 and deleted is false", data['username'])
    recent = await request.app.db.fetchrow("SELECT key, node FROM uploads WHERE username = $1 and deleted is false ORDER BY time DESC", data['username'])
    if not amount and not recent:
        return web.Response(status=400, reason="User not found/no entries")

    return web.json_response({
        "upload_count": amount,
        "last_upload": f"https://{request.app.settings['child_site']}/{recent['node']}/{recent['key']}"
    })

@router.get("/api/cdn/list/user/{user}")
async def get_cdn_list(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/cdn/list/user"):
        return web.Response(text="401 Unauthorized", status=401)

    usr = request.match_info.get("user", auth)

    values = await request.app.db.fetch("SELECT key, node FROM uploads WHERE username = $1 AND deleted is false;", usr)
    return web.json_response([{"key": rec['key'], "node": rec['node']} for rec in values])
