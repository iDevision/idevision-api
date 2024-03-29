import time
import traceback
import logging

import asyncpg
from aiohttp import web
from utils import handler, app

router = web.RouteTableDef()

logger = logging.getLogger("site")

def setup(app):
    app.add_routes(router)

@router.post("/api/cdn/nodes")
@handler.ratelimit(0, 0, ignore_logging=True)
async def post_node(request: app.TypedRequest, conn: asyncpg.Connection):
    if "Authorization" not in request.headers:
        return web.Response(status=401, text="Unauthorized")

    if request.headers.get("Authorization") != request.app.settings['slave_key']:
        return web.Response(status=401, text="Unauthorized")
    try:
        data = await request.json()
        port = int(data['port'])
        name = data['name']
        new = data.get("new", False)
    except Exception as e:
        print(e)
        return web.Response(status=400, text="Bad json")

    node = data.get("node", None)
    if node is not None:
        try:
            node = int(node)
        except:
            return web.Response(status=401, text="Invalid node contents")

    ip = request.headers.get("X-Forwarded-For", None) or request.remote

    if not node or new:
        if not new:
            d = await conn.fetchrow("SELECT node, name FROM slaves WHERE ip = $1 and port = $2", ip, port)
            if d:
                request.app.slaves[d['node']] = {"ip": ip, "port": port, "name": d['name'], "id": d['node'], "signin": time.time()}
                return web.json_response({"node": d['node'], "port": port, "ip": ip, "name": d['name']}, status=200)
        try:
            if name is not None:
                query = """
                INSERT INTO
                slaves (name, ip, port)
                VALUES
                ($1, $2, $3)
                RETURNING node, name
                """
                d = await conn.fetchrow(query, name, ip, port)
            else:
                query = """
                INSERT INTO
                slaves (name, ip, port)
                VALUES
                (
                    'node-' || ((SELECT COUNT(*) FROM slaves)+1),
                    $1,
                    $2
                )
                RETURNING node, name
                """
                try:
                    d = await conn.fetchrow(query, ip, port)
                except asyncpg.UniqueViolationError:
                    return web.Response(status=400, text="Node Exists.")

            request.app.slaves[d['node']] = {"ip": ip, "port": port, "name": d['name'], "id": d['node'], "signin": time.time()}
            return web.json_response({"node": d['node'], "port": port, "name": d['name'], "ip": ip}, status=201) # we've made a new slave
        except Exception as e:
            logger.error(f"error while making new node {name=} {ip=} {port=}", exc_info=e)
            print(f"Unable to make new node for {name=} {ip=} {port=}")
            return web.Response(status=500, reason="An error occured while making a new slave.")

    else:
        data = await conn.fetchrow("SELECT * FROM slaves WHERE port = $1 AND node = $2 AND ip = $3", port, node, ip)
        if not data:
            return web.Response(status=400, text="Node mismatch")

        request.app.slaves[data['node']] = {"ip": ip, "port": port, "name": data['name'], "id": data['node'], "signin": time.time()}
        return web.json_response({"node": data['node'], "port": port, "name": data['name'], "ip": ip})

@router.get("/api/cdn/nodes")
@handler.ratelimit(0, 0)
async def get_nodes(request: app.TypedRequest, conn: asyncpg.Connection):
    safe = request.query.get("safe", "").lower() == "true"

    slaves = request.app.slaves
    if safe:
        slaves = {i: {x: y for x, y in n.items() if x != "ip"} for i, n in slaves.items()}
    else:
        slaves = {i: n.copy() for i, n in slaves.items()}

    for x in slaves.values():
        x['signin'] = time.time() - x['signin']

    return web.json_response(slaves)
