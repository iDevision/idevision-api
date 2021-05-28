import random
import datetime
import aiohttp
import itertools
import time
import mimetypes
import json

import asyncpg
import yarl

from aiohttp import web

from utils import handler, app

router = web.RouteTableDef()

@router.get("/api/cdn")
@handler.ratelimit(20, 60)
async def get_cdn_stats(request: app.TypedRequest, conn: asyncpg.Connection):
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

async def upload_media_to_slaves(
        app,
        target: dict,
        stream,
        content_type: str,
        filename: str,
        conn: asyncpg.Connection,
        user: str,
        new_filename: str = None,
        allowed_access: list=None,
        expiry: datetime.datetime=None
    ):
    url = yarl.URL(f"http://{target['ip']}").with_port(target['port']).with_path("create")
    if new_filename:
        url = url.with_query(name=new_filename)

    async with aiohttp.ClientSession() as session: # cant use a global session because that would limit us to one at a time
        # also i cant be asked to make a clientsession pool
        async with session.post(url, data=stream,
                                headers={
                                    "Authorization": app.settings['slave_key'],
                                    "Content-Type": content_type,
                                    "File-Name": filename
                                }) as resp:
            if resp.status == 600:
                return False, await resp.text()
            elif 100 >= resp.status >= 300:
                return False, await resp.text()
            else:
                data = await resp.text()
                data = json.loads(data)
                new_name = data['name']
                path = data['path']
                node = data['node']
                size = data['size']

    await conn.execute(
        "INSERT INTO uploads VALUES ($1,$2,$3,0,$4,$5,$6,false,$7,$8)",
        new_name, user, datetime.datetime.utcnow(), allowed_access, path, node, size, expiry
    )
    return True, f"https://{app.settings['child_site']}/{target['name']}/{new_name}"

@router.post("/api/cdn")
@handler.ratelimit(3, 7)
async def post_media(request: app.TypedRequest, conn: asyncpg.Connection):
    allowed_auths = request.query.getall("authorized", None)
    target: str = request.query.get("node", None)

    if "content-type" not in request.headers and "file-name" not in request.headers:
        return web.Response(status=400, reason="Bad request. Missing a MIME type or 'file-name' header.")

    if "content-type" in request.headers:
        f_name = "file." + mimetypes.guess_extension(request.headers['content-type'].split(";")[0].strip())
    else:
        f_name = request.headers['file-name']

    if target and "cdn.manage" in request.user['permissions']:
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
        ct = mimetypes.guess_type(f_name, False)
        if not ct:
            ct = "text/plain"
        else:
            ct = ct[0]
        async with session.post(url, data=request.content,
                                headers={
                                    "Authorization": request.app.settings['slave_key'],
                                    "Content-Type": ct,
                                    "File-Name": f_name
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
        new_name, request.user['username'], datetime.datetime.utcnow(), allowed_auths, path, node, size
    )
    request.app.last_upload = f"https://{request.app.settings['child_site']}/{target['name']}/{new_name}"

    return web.json_response({
        "url": f"https://{request.app.settings['child_site']}/{target['name']}/{new_name}",
        "slug": new_name,
        "node": target['name']
    }, status=201)


@router.get("/api/cdn/{node}/{slug}")
@handler.ratelimit(15, 60)
async def get_upload_stats(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], "administrator" in request.user['permissions']

    if not admin and "cdn.upload" not in perms:
        return web.Response(reason="401 Unauthorized", status=401)

    key = request.match_info.get("slug")
    node = request.match_info.get("node")

    query = """
    SELECT key, time, username, views, size, slaves.name, expiry
    FROM uploads
    INNER JOIN slaves
        ON slaves.node = uploads.node
    WHERE key = $1
    AND uploads.node = (SELECT slaves.node FROM slaves WHERE slaves.name = $2)
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
        "size": about['size'],
        "expiry": about['expiry'] and about['expiry'].isoformat()
    })


@router.delete("/api/cdn/{node}/{slug}")
@handler.ratelimit(7, 60, "cdn.manage")
async def delete_image(request: app.TypedRequest, conn: asyncpg.Connection):
    node = request.match_info.get("node")

    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms = request.user['username'], request.user['permissions']

    manage = "cdn.manage" in perms

    if "cdn.upload" not in perms:
        return web.Response(reason="401 Unauthorized", status=401)

    target = None
    for n in request.app.slaves.values():
        if node == n['name']:
            target = n
            break

    if target is None:
        return web.Response(status=400, reason=f"Node '{node}' is unavailable or does not exist")

    if manage:
        coro = conn.fetchrow(
            "UPDATE uploads SET deleted = true WHERE key = $1 AND node = $2 RETURNING *;",
            request.match_info.get("slug"),
            target['id']
        )

    else:
        coro = conn.fetchrow(
            "UPDATE uploads SET deleted = true WHERE key = $1 AND node = $2 AND username = $3 RETURNING *;",
            request.match_info.get("image"),
            target['id'],
            auth
        )

    if not await coro:
        if manage:
            return web.Response(status=404)

        return web.Response(status=401, reason="401 Unauthorized")

    url = yarl.URL(f"http://{target['ip']}").with_port(target['port']).with_path("delete")

    async with aiohttp.ClientSession() as session:
        async with session.post(
                url,
                data=request.match_info.get("slug"),
                headers={"Authorization": request.app.settings['slave_key']}
        ) as resp:
            if 200 <= resp.status < 300:
                await conn.execute("UPDATE uploads SET deleted = false WHERE key = $1 and node = $2", request.match_info.get("slug"), node) # undo

            return web.Response(status=resp.status, reason=resp.reason)

@router.post("/api/cdn/purge")
@handler.ratelimit(0, 0)
async def purge_user(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
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
@handler.ratelimit(15, 60, "cdn.manage")
async def get_cdn_list(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms = request.user['username'], request.user['permissions']
    manage = "cdn.manage" in perms

    if not manage:
        raise web.HTTPFound("/api/cdn/list/"+auth)

    node = request.query.get("node", None)
    sort = request.query.get("sort", "user")
    if sort not in ("user", "node", "nodename"):
        return web.Response(reason="sort must be one of user, node, nodename", status=400)

    query = """
    SELECT
        key, uploads.node, slaves.name, username
    FROM uploads
    INNER JOIN slaves
        ON slaves.node = uploads.node
    WHERE deleted IS false
    """
    vals = []
    if node:
        vals.append(node)
        query += "AND uploads.node = (SELECT slaves.node FROM slaves WHERE slaves.name = $1)"

    values = await conn.fetch(query, *vals)
    resp = {}
    if sort == "user":
        for rec in values:
            if rec['username'] in resp:
                resp[rec['username']].append({"key": rec['key'], "node_id": rec['node'], "node": rec['name']})
            else:
                resp[rec['username']] = [{"key": rec['key'], "node_id": rec['node'], "node": rec['name']}]

    elif sort == "node":
        for rec in values:
            if rec['node'] in resp:
                resp[rec['node']].append({"key": rec['key'], "node_id": rec['node'], "node": rec['name']})
            else:
                resp[rec['node']] = [{"key": rec['key'], "node_id": rec['node'], "node": rec['name']}]

    elif sort == "nodename":
        for rec in values:
            if rec['name'] in resp:
                resp[rec['name']].append({"key": rec['key'], "node_id": rec['node'], "node": rec['name']})
            else:
                resp[rec['name']] = [{"key": rec['key'], "node_id": rec['node'], "node": rec['name']}]

    return web.json_response(resp)

@router.get("/api/cdn/list/{user}")
@handler.ratelimit(15, 60, "cdn.manage")
async def get_cdn_list(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms = request.user['username'], request.user['permissions']
    usr = request.match_info.get("user", auth)

    if usr != auth and "cdn.manage" not in perms:
        return web.Response(reason="401 Unauthorized", status=401)

    values = await conn.fetch("SELECT key, node, size FROM uploads WHERE username = $1 AND deleted is false ORDER BY time;", usr)
    return web.json_response([{"key": rec['key'], "node": rec['node'], "size": rec['size']} for rec in values])

@router.get("/api/cdn/user")
@handler.ratelimit(15, 60, "cdn.manage")
async def get_user_stats(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms = request.user['username'], request.user['permissions']
    usr = request.query.get("username", auth)

    if usr != auth and "cdn.manage" not in perms:
        return web.Response(reason="401 Unauthorized", status=401)

    amount = await conn.fetchval("SELECT COUNT(*) FROM uploads WHERE username = $1 and deleted is false", usr)
    recent = await conn.fetchrow("SELECT key, slaves.name FROM uploads INNER JOIN slaves ON slaves.node = uploads.node WHERE username = $1 and deleted is false ORDER BY time DESC LIMIT 1", usr)
    if not amount and not recent:
        return web.Response(status=400, reason="User not found/no entries")

    return web.json_response({
        "upload_count": amount,
        "last_upload": f"https://{request.app.settings['child_site']}/{recent['name']}/{recent['key']}"
    })
