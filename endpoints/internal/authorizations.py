import os
import secrets

import asyncpg
from aiohttp import web

import utils

router = web.RouteTableDef()

@router.post("/api/internal/users/apply")
async def apply(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    try:
        data = await request.json()
    except:
        return web.Response(text="400 Invalid JSON", status=400)

    async with request.app.db.acquire() as conn:
        try:
            declined = await conn.fetchrow("SELECT decline_reason, auths.discord_id AS exists FROM applications INNER JOIN auths ON auths.discord_id = $1 WHERE userid = $1", data['userid'])
            if declined is not None and declined['decline_reason']:
                return web.Response(text=f"Your application has been declined for the following reason: {declined['decline_reason']}", status=403)
            elif declined is not None and declined['exists']:
                return web.Response(text="You already have an account", status=403)

            await conn.execute("INSERT INTO applications VALUES ($1, $2, $3, $4)", data['userid'], data['username'], data['reason'], data['routes'])
        except KeyError as e:
            return web.Response(text=f"Missing {e.args[0]} body value", status=400)
        except asyncpg.UniqueViolationError:
            return web.Response(text="Already Applied", status=403)
        else:
            return web.Response(status=201)

@router.post("/api/internal/users/accept")
async def accept_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    try:
        data = await request.json()
        userid = data['userid']
    except:
        return web.Response(text="400 Invalid JSON", status=400)

    application = await request.app.db.fetchrow("DELETE FROM applications WHERE userid = $1 RETURNING userid, username, routes", userid)

    if application is None:
        return web.Response(status=400, text="Application not found")

    token = f"user.{application['username']}.{secrets.token_urlsafe(25)}"
    await request.app.db.execute(
        "INSERT INTO auths VALUES ($1, $2, $3, true, $4, false)",
        application['username'], token, application['routes'], application['userid']
    )
    return web.json_response({"token": token}, status=201)

@router.post("/api/internal/users/deny")
async def deny_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    try:
        data = await request.json()
        userid = data['userid']
        reason = data['reason']
        allow_retry = data['retry']
    except:
        return web.Response(text="400 Invalid JSON", status=400)

    if not allow_retry:
        application = await request.app.db.fetchrow(
            "UPDATE applications SET decline_reason = $1 WHERE userid = $2 RETURNING userid",
            reason, userid
        )
    else:
        application = await request.app.db.fetchrow(
            "DELETE FROM applications WHERE userid = $1 RETURNING userid",
            userid
        )

    if application is None:
        return web.Response(status=400, reason="Application not found")

    return web.Response(status=204)

@router.post("/api/internal/users/token")
async def generate_token(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    async with request.app.db.acquire() as conn:
        try:
            data = await request.json()
            if "discord_id" in data:
                username = await conn.fetchval("SELECT username FROM auths WHERE discord_id = $1", data['discord_id'])
            elif "username" in data:
                username = data['username']
            else:
                username = auth
            if username != auth and not utils.route_allowed(routes, "api/internal/users/manage"):
                return web.Response(text="401 Unauthorized", status=401)
        except:
            return web.Response(text="Invalid JSON", status=400)

        new_token = f"user.{username}.{secrets.token_urlsafe(25)}"
        if await conn.fetchval("UPDATE auths SET auth_token = $1 WHERE username = $2 RETURNING username", new_token, username) is not None:
            return web.json_response({"token": new_token})
        else:
            return web.Response(status=400, text="Account not found", reason="Account not found")


@router.post("/api/internal/users/manage")
async def add_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    routes = [x.strip("/") for x in data.get("routes", [])]
    if request.app.test:
        return web.Response(status=204)

    await request.app.db.execute("INSERT INTO auths VALUES ($1, $2, $3, true)", data['username'], data['authorization'], routes)
    return web.Response(status=204)

@router.delete("/api/internal/users/manage")
async def remove_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if request.app.test:
        return web.Response(status=204)

    data = await request.app.db.fetch("SELECT key FROM uploads WHERE username = $1", usr)
    for row in data:
        os.remove("/var/www/idevision/media/" + row['key'])

    await request.app.db.execute("DELETE FROM auths WHERE username = $1", usr)
    return web.Response(status=204)

@router.post("/api/internal/users/deauth")
async def deauth_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")

    if request.app.test:
        return web.Response(status=204)

    await request.app.db.fetchrow("UPDATE auths SET active = false WHERE username = $1", usr)
    return web.Response(status=204)

@router.post("/api/internal/users/auth")
async def auth_user(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/users/manage"):
        return web.Response(text="401 Unauthorized", status=401)

    data = await request.json()
    usr = data.get("username")
    if request.app.test:
        return web.Response(status=204)

    await request.app.db.fetchrow("UPDATE auths SET active = true WHERE username = $1", usr)
    return web.Response(status=204)

@router.get("/api/bans")
async def get_bans(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/bans"):
        return web.Response(text="401 Unauthorized", status=401)

    ip = request.query.get("ip")
    useragent = request.query.get("user-agent")
    offset = request.query.get("offset")
    if offset:
        try:
            offset = int(offset)
        except:
            return web.Response(status=400, reason="Bad offset parameter")
    else:
        offset = 0

    if ip and useragent:
        resp = await request.app.db.fetch("SELECT * FROM bans WHERE ip = $1 AND similarity($2, user_agent) > 0.8 LIMIT 50 OFFSET $3", ip, useragent, offset)
    elif ip:
        resp = await request.app.db.fetch("SELECT * FROM bans WHERE ip = $1 LIMIT 50 OFFSET $2", ip, offset)
    elif useragent:
        resp = await request.app.db.fetch("SELECT * FROM bans WHERE similarity($1, user_agent) > 0.8 LIMIT 50 OFFSET $2", offset)
    else:
        resp = await request.app.db.fetch("SELECT * FROM bans LIMIT 50 OFFSET $1", offset)

    return web.json_response({"bans": [dict(x) for x in resp]})

@router.post("/api/internal/bans")
async def create_ban(request: utils.TypedRequest):
    auth, routes = await utils.get_authorization(request, request.headers.get("Authorization"))
    if not auth:
        return web.Response(text="401 Unauthorized", status=401)

    if not utils.route_allowed(routes, "api/internal/bans"):
        return web.Response(text="401 Unauthorized", status=401)

    ip = request.query.get("ip")
    useragent = request.query.get("user-agent")
    reason = request.query.get("reason")
    await request.app.db.fetchrow("INSERT INTO bans (ip, user_agent, reason) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", ip, useragent, reason)
    return web.Response(status=201)