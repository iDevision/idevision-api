import random
import datetime
import aiohttp
import itertools
import time
import json

import asyncpg
import yarl

from aiohttp import web

from utils import ratelimit, utils

router = web.RouteTableDef()

@router.get("/api/cdn")
@ratelimit(20, 60)
async def get_cdn_stats(request: utils.TypedRequest, conn: asyncpg.Connection):
    amount = await conn.fetchrow("""
    SELECT
        (SELECT COUNT(*) FROM uploads WHERE deleted is false) AS allcount,
        (SELECT COUNT(*) FROM uploads WHERE time > ((now() at time zone 'utc') - INTERVAL '1 day')) AS todaycount,
        (SELECT cast('https://{child_site}/' as text) || slaves.name || cast('/' as text) || uploads.key FROM uploads INNER JOIN slaves ON 
            slaves.node = uploads.node ORDER BY time DESC LIMIT 1) as last_upload;
    """)

    return web.json_response({
        "upload_count": amount['allcount'],
        "uploaded_today": amount['todaycount'],
        "last_upload": amount['last_upload'].format(child_site=request.app.settings['child_site'])
    })

@router.post("/api/cdn")
@ratelimit(3, 7)
async def post_media(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "cdn"):
        return web.Response(reason="401 Unauthorized", status=401)

    allowed_auths = request.query.getall("authorized", None)
    target: str = request.query.get("node", None)

    if target and (utils.route_allowed(perms, "users.manage") or admin):
        name: str = request.query.get("name", None)

        if target.isnumeric():
            target: int = int(target)
            if target not in request.app.slaves:
                return web.Response(status=400, reason="The specified node is not available")

            target: dict = request.app.slaves[target]
        else:
            for _node in request.app.slaves.values():
                if _node['name'].lower() == target.lower():
                    target: dict = _node
                    break

        if type(target) is str:
            return web.Response(status=400, reason="The specified node is not available")

        elif time.time() - target['signin'] > 300:
            return web.Response(status=400, reason="The specified node is not available")

    else:
        name = None
        t = time.time()
        options = {x: y for x, y in request.app.slaves.items() if t-y['signin'] < 300 and y['name'] not in request.app.settings['slave_no_balancing']}
        if not options:
            return web.Response(status=503, reason="Error: no nodes available")

        target = random.choice(list(options.keys()))
        target = options[target]

    url = yarl.URL(f"http://{target['ip']}").with_port(target['port']).with_path("create")
        # use http to directly access the backend, cuz it probably isnt behind nginx

    if name is not None:
        url = url.with_query(name=name)

    async with aiohttp.ClientSession() as session: # cant use a global session because that would limit us to one at a time
        # also i cant be asked to make a clientsession pool
        async with session.post(url, data=request.content,
                                headers={
                                    "Authorization": request.app.settings['slave_key'],
                                    "Content-Type": request.headers.get("Content-Type"),
                                    "File-Name": request.headers.get("File-Name", "upload.jpg")
                                }) as resp:
            if resp.status == 600:
                return web.Response(status=400, reason=await resp.text())
            elif 100 >= resp.status >= 300:
                return web.Response(status=500, reason=await resp.text())
            else:
                data = await resp.text()
                data = json.loads(data)
                new_name = data['name']
                path = data['path']
                node = data['node']
                size = data['size']

    await conn.execute(
        "INSERT INTO uploads VALUES ($1,$2,$3,0,$4,$5,$6,false,$7)",
        new_name, auth, datetime.datetime.utcnow(), allowed_auths, path, node, size
    )
    request.app.last_upload = f"https://{request.app.settings['child_site']}/{target['name']}/{new_name}"

    return web.json_response({
        "url": f"https://{request.app.settings['child_site']}/{target['name']}/{new_name}",
        "slug": new_name,
        "node": target['name']
    }, status=201)


@router.get("/api/cdn/{node}/{slug}")
@ratelimit(15, 60)
async def get_upload_stats(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "cdn"):
        return web.Response(reason="401 Unauthorized", status=401)

    key = request.match_info.get("slug")
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
    about = await conn.fetchrow(query, key, node)
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


@router.delete("/api/cdn/{node}/{slug}")
@ratelimit(7, 60, "cdn.manage")
async def delete_image(request: utils.TypedRequest, conn: asyncpg.Connection):
    node = request.match_info.get("node")

    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "cdn"):
        return web.Response(reason="401 Unauthorized", status=401)

    target = None
    for n in request.app.slaves:
        if node == n['name']:
            target = n

    if target is None:
        return web.Response(status=400, reason="Node is unavailable or does not exist")

    if admin or utils.route_allowed(perms, "cdn.manage"):
        coro = conn.fetchrow(
            "UPDATE uploads SET deleted = true WHERE key = $1 AND node = $2 RETURNING *;",
            request.match_info.get("slug"),
            node
        )

    else:
        coro = conn.fetchrow(
            "UPDATE uploads SET deleted = true WHERE key = $1 AND node = $2 AND username = $3 RETURNING *;",
            request.match_info.get("image"),
            node,
            auth
        )
    if not await coro:
        if admin or utils.route_allowed(perms, "cdn.manage"):
            return web.Response(status=404)

        return web.Response(status=401, reason="401 Unauthorized")

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
@ratelimit(1, 1, "cdn.manage")
async def purge_user(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "cdn.manage"):
        return web.Response(reason="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if request.app.test:
        return web.Response(status=204)

    active_slaves = list(request.app.slaves.keys())
    data = await conn.fetch("UPDATE uploads SET deleted = true WHERE username = $1 AND node = ANY($2) RETURNING *;", usr, active_slaves)
    if not data:
        return web.Response(status=400, reason="User not found/no images to delete")

    session = aiohttp.ClientSession(headers={"Authorization": request.app.settings['slave_key']})

    for group, vals in itertools.groupby(data, key=lambda r: r['node']):
        node = request.app.slaves[group]
        url = yarl.URL(f"http://{node['ip']}").with_port(node['port']).with_path("mass-delete") # TODO: mass delete on slave end
        async with session.post(url, json={"ids": [x['id'] for x in vals]}) as resp:
            pass

    await session.close()
    return web.Response()

@router.get("/api/cdn/list")
@ratelimit(15, 60, "cdn.manage")
async def get_cdn_list(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']

    if not admin and not utils.route_allowed(perms, "cdn.manage"):
        raise web.HTTPFound("/api/cdn/list/"+auth)

    query = """
    SELECT
        key, node, slaves.name, username
    FROM uploads
    INNER JOIN slaves
        ON slaves.node = uploads.node
    WHERE deleted IS false
    """
    values = await conn.fetch(query)
    resp = {}
    for rec in values:
        if rec['username'] in resp:
            resp[rec['username']].append({"key": rec['key'], "node": rec['name']})
        else:
            resp[rec['username']] = [{"key": rec['key'], "node": rec['name']}]

    return web.json_response(resp)

@router.get("/api/cdn/list/{user}")
@ratelimit(15, 60, "cdn.manage")
async def get_cdn_list(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']
    usr = request.match_info.get("user", auth)

    if usr != auth and not admin and not utils.route_allowed(perms, "cdn.manage"):
        return web.Response(reason="401 Unauthorized", status=401)

    values = await conn.fetch("SELECT key, node, size FROM uploads WHERE username = $1 AND deleted is false ORDER BY time;", usr)
    return web.json_response([{"key": rec['key'], "node": rec['node'], "size": rec['size']} for rec in values])

@router.get("/api/cdn/user")
@ratelimit(15, 60, "cdn.manage")
async def get_user_stats(request: utils.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], request.user['administrator']
    usr = request.query.get("username", auth)

    if usr != auth and not admin and not utils.route_allowed(perms, "cdn.manage"):
        return web.Response(reason="401 Unauthorized", status=401)

    amount = await conn.fetchval("SELECT COUNT(*) FROM uploads WHERE username = $1 and deleted is false", usr)
    recent = await conn.fetchrow("SELECT key, slaves.name FROM uploads INNER JOIN slaves ON slaves.node = uploads.node WHERE username = $1 and deleted is false ORDER BY time DESC LIMIT 1", usr)
    if not amount and not recent:
        return web.Response(status=400, reason="User not found/no entries")

    return web.json_response({
        "upload_count": amount,
        "last_upload": f"https://{request.app.settings['child_site']}/{recent['name']}/{recent['key']}"
    })
