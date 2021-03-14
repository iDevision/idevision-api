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
    except:
        return web.Response(status=400, text="Bad json")

    node = data.get("node", None)
    if node is not None:
        try:
            node = int(node)
        except:
            return web.Response(status=401, text="Invalid node contents")

    ip = request.headers.get("X-Forwarded-For", None) or request.remote

    if not node:
        d = await request.app.db.fetchrow("SELECT node FROM slaves WHERE ip = $1", ip)
        if d:
            request.app.slaves[data['node']] = {"ip": ip, "port": port, "signin": time.time()}
            return web.json_response({"node": data['node'], "port": port, "ip": ip}, status=200)

        data = await request.app.db.fetchrow("INSERT INTO slaves (ip, port) VALUES ($1, $2) RETURNING node", ip, port)
        request.app.slaves[data['node']] = {"ip": ip, "port": port, "signin": time.time()}
        return web.json_response({"node": data['node'], "port": port, "ip": ip}, status=201) # we've made a new node

    else:
        data = await request.app.db.fetchrow("UPDATE slaves SET port = $1 WHERE node = $2 AND ip = $3 RETURNING *", port, node, ip)
        if not data:
            return web.Response(status=400, text="Node mismatch")

        request.app.slaves[data['node']] = {"ip": ip, "port": port, "signin": time.time()}
        return web.json_response({"node": node, "port": port, "ip": ip})
