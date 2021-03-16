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

@router.get("/api/cdn")
async def get_cdn_stats(request: utils.TypedRequest):
    amount = await request.app.db.fetchrow("SELECT "
        "(SELECT COUNT(*) FROM uploads WHERE deleted is false) AS allcount, "
        "(SELECT COUNT(*) FROM uploads WHERE time > ((now() at time zone 'utc') - INTERVAL '1 day')) AS todaycount;")

    return web.json_response({
        "upload_count": amount['allcount'],
        "uploaded_today": amount['todaycount'],
        "last_upload": request.app.last_upload
    })

@router.post("/api/cdn")
async def post_media(request: utils.TypedRequest):
    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not admin and not utils.route_allowed(routes, "cdn.upload"):
        return web.Response(text="401 Unauthorized", status=401)

    allowed_auths = request.query.getall("authorized", None)
    target: str = request.query.get("node", None)
    if target and (utils.route_allowed(routes, "users.manage") or admin):
        if target.isnumeric():
            target: int = int(target)
            if target not in request.app.slaves:
                return web.Response(status=400, text="The specified node is not available")

            target: dict = request.app.slaves[target]
        else:
            for _node in request.app.slaves.values():
                if _node['name'].lower() == target.lower():
                    target: dict = _node
                    break

        if type(target) is str:
            return web.Response(status=400, text="The specified node is not available")
        elif time.time() - target['signin'] > 300:
            return web.Response(status=400, text="The specified node is not available")

    else:
        t = time.time()
        options = {x: y for x, y in request.app.slaves.items() if t-y['signin'] < 300 and y['name'] not in request.app.settings['slave_no_balancing']}
        if not options:
            return web.Response(status=503, text="Error: no nodes available")

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
                size = data['size']

    await request.app.db.execute(
        "INSERT INTO uploads VALUES ($1,$2,$3,0,$4,$5,$6,false,$7)",
        new_name, auth, datetime.datetime.utcnow(), allowed_auths, path, node, size
    )
    request.app.last_upload = new_name

    return web.json_response({
        "url": f"https://{request.app.settings['child_site']}/{target['name']}/{new_name}",
        "slug": new_name,
        "name": new_name,
        "node": target['name']
    }, status=200)

@router.get("/api/cdn/{node}/{image}")
async def get_upload_stats(request: utils.TypedRequest):
    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not admin and not utils.route_allowed(routes, "cdn"):
        return web.Response(text="401 Unauthorized", status=401)

    key = request.match_info.get("key")
    node = request.match_info.get("node")

    query = """
    SELECT key, time, username, views, size, slaves.name
    FROM uploads
    INNER JOIN slaves
        ON slaves.node = uploads.node
    WHERE key = $1
    AND node = (SELECT node FROM slaves WHERE name = $2)
    AND deleted IS false
    """
    about = await request.app.db.fetchrow(query, key, node)
    if not about:
        return web.Response(status=404)

    return web.json_response({
        "url": f"https://{request.app.settings['child_site']}/{about['name']}/{about['key']}",
        "timestamp": about['time'].timestamp(),
        "author": about['username'],
        "views": about['views'],
        "node": about['name'],
        "size": about['size']
    })


@router.delete("/api/cdn/{node}/{image}")
async def delete_image(request: utils.TypedRequest):
    node = request.match_info.get("node")
    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not admin and not utils.route_allowed(routes, "cdn.upload"):
        return web.Response(text="401 Unauthorized", status=401)

    target = None
    for n in request.app.slaves:
        if node == n['name']:
            target = n

    if target is None:
        return web.Response(status=400, text="Node is unavailable or does not exist")

    if admin or utils.route_allowed(routes, "cdn.manage"):
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
        if admin or utils.route_allowed(routes, "cdn.manage"):
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

@router.post("/api/cdn/purge")
async def purge_user(request: utils.TypedRequest):
    return web.Response(status=501)
    # TODO

    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not admin and not utils.route_allowed(routes, "cdn.manage"):
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

@router.get("/api/cdn/list")
async def get_cdn_list(request: utils.TypedRequest):
    return web.Response(status=501)
    # TODO

    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not admin and not utils.route_allowed(routes, "cdn.manage"):
        raise web.HTTPFound("/api/cdn/list/"+auth)

    query = """
    SELECT
        key, node, slaves.name, username
    FROM uploads
    INNER JOIN slaves
        ON slaves.node = uploads.node
    WHERE deleted IS false
    """
    values = await request.app.db.fetch(query)
    resp = {}
    for rec in values:
        if rec['username'] in resp:
            resp[rec['username']].append({"key": rec['key'], "node": rec['name']})
        else:
            resp[rec['username']] = [{"key": rec['key'], "node": rec['name']}]

    return web.json_response(resp)

@router.get("/api/cdn/list/{user}")
async def get_cdn_list(request: utils.TypedRequest):
    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    usr = request.match_info.get("user", auth)

    if usr != auth and not admin and not utils.route_allowed(routes, "cdn.manage"):
        return web.Response(text="401 Unauthorized", status=401)

    values = await request.app.db.fetch("SELECT key, node, size FROM uploads WHERE username = $1 AND deleted is false ORDER BY time;", usr)
    return web.json_response([{"key": rec['key'], "node": rec['node'], "size": rec['size']} for rec in values])

@router.get("/api/cdn/user")
async def get_user_stats(request: utils.TypedRequest):
    auth, routes, admin = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    usr = request.query.get("username", auth)

    if usr != auth and not admin and not utils.route_allowed(routes, "cdn.manage"):
        return web.Response(text="401 Unauthorized", status=401)

    amount = await request.app.db.fetchval("SELECT COUNT(*) FROM uploads WHERE username = $1 and deleted is false", usr)
    recent = await request.app.db.fetchrow("SELECT key, node FROM uploads WHERE username = $1 and deleted is false ORDER BY time DESC", usr)
    if not amount and not recent:
        return web.Response(status=400, reason="User not found/no entries")

    return web.json_response({
        "upload_count": amount,
        "last_upload": f"https://{request.app.settings['child_site']}/{recent['node']}/{recent['key']}"
    })
