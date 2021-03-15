import time

from aiohttp import web
import utils

router = web.RouteTableDef()

def setup(app):
    app.add_routes(router)

@router.post("/api/cdn/nodes")
async def post_node(request: utils.TypedRequest):
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
            d = await request.app.db.fetchrow("SELECT node, name FROM slaves WHERE ip = $1", ip)
            if d:
                request.app.slaves[d['node']] = {"ip": ip, "port": port, "name": d['name'], "id": d['node'], "signin": time.time()}
                return web.json_response({"node": d, "port": port, "ip": ip, "name": d['name']}, status=200)

        d = await request.app.db.fetchrow("""
        INSERT INTO
        slaves (name, ip, port)
        VALUES
        (
            CASE
                WHEN $1 IS NULL
                    THEN 'node-' || (SELECT COUNT(*) FROM slaves)
                ELSE $1
            END,
            $2,
            $3
        )
        RETURNING node, name
        """, name, ip, port)
        request.app.slaves[d['node']] = {"ip": ip, "port": port, "name": d['name'], "id": d['node'], "signin": time.time()}
        return web.json_response({"node": d['node'], "port": port, "name": d['name'], "ip": ip}, status=201) # we've made a new slave

    else:
        data = await request.app.db.fetchrow("UPDATE slaves SET port = $1 WHERE node = $2 AND ip = $3 RETURNING *", port, node, ip)
        if not data:
            return web.Response(status=400, text="Node mismatch")

        request.app.slaves[data['node']] = {"ip": ip, "port": port, "name": name, "id": data['node'], "signin": time.time()}
        return web.json_response({"node": data['node'], "port": port, "name": name, "ip": ip})
