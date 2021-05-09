import asyncpg
from aiohttp import web

from utils import handler, app

router = web.RouteTableDef()

@router.get("/api/internal/routes")
@handler.ratelimit(0, 0)
async def get_routes(request: app.TypedRequest, conn: asyncpg.Connection):
    resp = {}

    all_routes = []
    for res in request.app.router._resources:
        if isinstance(res, web.PlainResource):
            for obj in res._routes:
                all_routes.append((res._path, obj.method))

    for endpoint in all_routes:
        if endpoint[1] == "HEAD":
            continue

        if endpoint[0] in resp:
            resp[endpoint[0]].append({"method": endpoint[1], "permission": request.app.route_permissions.get(
                (endpoint[0], endpoint[1]), None)})
        else:
            resp[endpoint[0]] = []
            resp[endpoint[0]].append({"method": endpoint[1], "permission": request.app.route_permissions.get(
                (endpoint[0], endpoint[1]), None)})

    return web.json_response(resp)

@router.get("/api/internal/permissions")
@handler.ratelimit(0, 0)
async def get_permissions(request: app.TypedRequest, conn: asyncpg.Connection):
    data = await conn.fetch("SELECT * FROM permissions")
    return web.json_response({"permissions": [x['name'] for x in data]})

@router.post("/api/internal/permissions")
@handler.ratelimit(0, 0)
async def add_permission(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        body = await request.json()
        perm = str(body['permission']).lower()
    except:
        return web.Response(status=400, reason="Bad Request")

    try:
        await conn.execute("INSERT INTO permissions VALUES ($1)", perm)
    except:
        return web.Response(status=400, reason="Permission already exists")

    return web.Response(status=204)

@router.post("/api/internal/routes")
@handler.ratelimit(0, 0)
async def add_route_perms(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        body = await request.json()
        endpoint = str(body['endpoint']).rstrip("/")
        method = str(body['method']).upper()
        permission = str(body['permission']).lower()
    except KeyError as e:
        return web.Response(status=400, reason=f"Missing {e} key")
    except:
        return web.Response(status=400, reason="Bad Request")

    if endpoint not in [x.get_info().get("path") for x in request.app.router._resources] and request.query.get("force", "").lower() != "true":
        return web.Response(status=400, reason="route does not exist")

    if not any([permission == perm for perm in request.app.route_permissions.values()]):
        try:
            await conn.execute("INSERT INTO permissions VALUES ($1) ON CONFLICT (name) DO NOTHING", permission)
        except:
            pass

    query = "INSERT INTO routes VALUES ($1, $2, $3) ON CONFLICT (route, method) DO UPDATE SET permission = $3"
    await conn.execute(query, endpoint, method, permission)
    request.app.route_permissions[(endpoint, method)] = permission

    return web.Response(status=204)

@router.delete("/api/internal/routes")
@handler.ratelimit(0, 0)
async def delete_route_perms(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        body = await request.json()
        endpoint = str(body['endpoint']).rstrip("/")
        method = str(body['method']).upper()
    except KeyError as e:
        return web.Response(status=400, reason=f"Missing {e} key")
    except:
        return web.Response(status=400, reason="Bad Request")

    if endpoint not in [x.get_info().get("path") for x in request.app.router._resources] and request.query.get("force", "").lower() != "true":
        return web.Response(status=400, reason="route does not exist")

    query = "DELETE FROM routes WHERE route = $1 AND method = $2"
    await conn.execute(query, endpoint, method)
    try:
        del request.app.route_permissions[(endpoint, method)]
    except:
        pass

    return web.Response(status=204)

@router.delete("/api/internal/permissions")
@handler.ratelimit(0, 0)
async def delete_permission(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        body = await request.json()
        permission = str(body['permission']).lower()
    except KeyError as e:
        return web.Response(status=400, reason=f"Missing {e} key")
    except:
        return web.Response(status=400, reason="Bad Request")

    query = "DELETE FROM permissions WHERE name = $1 RETURNING *"
    if await conn.fetch(query, permission):
        return web.Response(status=204)

    return web.Response(status=400, reason="Permission does not exist")

