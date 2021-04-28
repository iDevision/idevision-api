import datetime
import secrets

import asyncpg
from aiohttp import web

from utils import handler, app

router = web.RouteTableDef()

@router.get("/api/internal/users")
@handler.ratelimit(5, 60, 'users.manage')
async def get_user(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(status=401)

    auth, perms, admin = request.user['username'], request.user['permissions'], "administrator" in request.user['permissions']

    if not admin and "internal.users.manage" not in perms:
        username = auth
        discord_id = None
    else:
        username = request.query.get("username", None)
        discord_id = request.query.get("discordid", None)

    if discord_id:
        try:
            discord_id = int(discord_id)
        except:
            return web.Response(status=400, reason="Expected an integer for discordid")

    if not username and not discord_id:
        return web.Response(reason="'username' and/or 'discordid' query parameters are required", status=400)

    v1 = "$1"
    v2 = "$2"
    query = f"""
    SELECT * FROM auths
    WHERE
    {'username = $1' if username else ''}
    {'OR' if username and discord_id else ''}
    {f'discord_id = {v1 if not username else v2}' if discord_id else ''}
    """
    data = await conn.fetchrow(query, *(x for x in (username, discord_id) if x is not None))
    if data:
        d = dict(data)
        if not admin:
            del d['auth_key']
            del d['active']

        return web.json_response(d)
    return web.Response(status=204)


@router.post("/api/internal/users/apply")
@handler.ratelimit(0, 0)
async def apply(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        data = await request.json()
    except:
        return web.Response(reason="400 Invalid JSON", status=400)

    try:
        declined = await conn.fetchrow("SELECT decline_reason, auths.discord_id AS exists FROM applications INNER JOIN auths ON auths.discord_id = $1 WHERE userid = $1", data['userid'])
        if declined is not None and declined['decline_reason']:
            return web.Response(reason=f"Your application has been declined for the following reason: {declined['decline_reason']}", status=403)

        elif declined is not None and declined['exists']:
            return web.Response(reason="You already have an account", status=403)

        await conn.execute("INSERT INTO applications VALUES ($1, $2, $3, $4)", data['userid'], data['username'], data['reason'], data['permissions'])
    except KeyError as e:
        return web.Response(reason=f"Missing {e.args[0]} body value", status=400)

    except asyncpg.UniqueViolationError:
        return web.Response(reason="Already Applied", status=403)
    else:
        return web.Response(status=201)

@router.post("/api/internal/users/accept")
@handler.ratelimit(0, 0)
async def accept_user(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        data = await request.json()
        userid = data['userid']
    except:
        return web.Response(reason="400 Invalid JSON", status=400)

    application = await conn.fetchrow("DELETE FROM applications WHERE userid = $1 RETURNING userid, username, routes", userid)

    if application is None:
        return web.Response(status=400, reason="Application not found")

    token = f"user.{application['username']}.{secrets.token_urlsafe(25)}"
    await conn.execute(
        "INSERT INTO auths VALUES ($1, $2, $3, true, $4, false)",
        application['username'], token, application['routes'], application['userid']
    )
    return web.json_response({"token": token}, status=201)

@router.post("/api/internal/users/deny")
@handler.ratelimit(0, 0)
async def deny_user(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        data = await request.json()
        userid = data['userid']
        reason = data['reason']
        allow_retry = data['retry']
    except:
        return web.Response(reason="400 Invalid JSON", status=400)

    if not allow_retry:
        application = await conn.fetchrow(
            "UPDATE applications SET decline_reason = $1 WHERE userid = $2 RETURNING userid",
            reason, userid
        )
    else:
        application = await conn.fetchrow(
            "DELETE FROM applications WHERE userid = $1 RETURNING userid",
            userid
        )

    if application is None:
        return web.Response(status=400, reason="Application not found")

    return web.Response(status=204)

@router.post("/api/internal/users/token")
@handler.ratelimit(1, 120, "users.manage")
async def generate_token(request: app.TypedRequest, conn: asyncpg.Connection):
    if not request.user:
        return web.Response(reason="401 Unauthorized", status=401)

    auth, perms = request.user['username'], request.user['permissions']

    try:
        data = await request.json()
        if "discord_id" in data:
            username = await conn.fetchval("SELECT username FROM auths WHERE discord_id = $1", data['discord_id'])

        elif "username" in data:
            username = data['username']

        else:
            username = auth
        if username != auth and "internal.users.manage" not in perms:
            return web.Response(reason="401 Unauthorized", status=401)
    except:
        return web.Response(reason="Invalid JSON", status=400)

    new_token = f"user.{username}.{secrets.token_urlsafe(25)}"
    if await conn.fetchval("UPDATE auths SET auth_key = $1 WHERE username = $2 RETURNING username", new_token, username) is not None:
        return web.json_response({"token": new_token})
    else:
        return web.Response(status=400, reason="Account not found")


@router.post("/api/internal/users")
@handler.ratelimit(0, 0, "internal.users.manage")
async def add_user(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        data = await request.json()
        userperms = data['permissions']
        assert isinstance(userperms, list), ValueError("permissions must be a list")
        discord_id = data.get("discord_id", None)
        assert discord_id is None or isinstance(discord_id, int), ValueError("discord_id must be an integer")
        ignores_ratelimits = data.get("ignores_ratelimits", False)
        assert isinstance(ignores_ratelimits, bool), ValueError("ignores_ratelimits must be a boolean")
    except (ValueError, AssertionError) as e:
        return web.Response(status=400, reason=e.args[0])
    except KeyError as e:
        return web.Response(status=400, reason=f"Body missing {e.args[0]} key")


    unallowed = tuple(perm for perm in userperms if perm not in request.user['permissions'])
    if unallowed and "administrator" not in request.user['permissions']:
        return web.Response(
            status=403,
            reason=f"You cannot assign the "
                   f"{','.join(unallowed)} permission(s)"
        )


    token = f"user.{data['username']}.{secrets.token_urlsafe(25)}"

    await conn.execute(
        "INSERT INTO auths VALUES ($1, $2, $3, true, $4, $5)",
        data['username'],
        token,
        userperms,
        discord_id,
        ignores_ratelimits
    )
    return web.json_response({"token": token})

@router.patch("/api/internal/users")
@handler.ratelimit(0, 0)
async def patch_user(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        data = await request.json()
        username = data['username']
        new_username = data.get("new_username", None)
        discord_id = data.get("discord_id", None)
        perms = data.get("permissions", None)
        ignores_ratelimits = data.get("ignores_ratelimits", None)
    except:
        return web.Response(status=400)

    unallowed = tuple(perm for perm in perms if perm not in request.user['permissions'])
    if unallowed and "administrator" not in request.user['permissions']:
        return web.Response(
            status=403,
            reason=f"You cannot assign the "
                   f"{','.join(unallowed)} permission(s)"
        )

    query = """
    UPDATE auths
    SET
        username = COALESCE($1, username),
        discord_id = COALESCE($2, discord_id),
        permissions = COALESCE($3, permissions),
        ignores_ratelimits = COALESCE($4, ignores_ratelimits)
    WHERE username = $5
    RETURNING username
    """
    if not await conn.fetchval(query, new_username, discord_id, perms, ignores_ratelimits, username):
        return web.Response(status=400, reason="User not found")

    return web.Response(status=204)

@router.post("/api/internal/users/deauth")
@handler.ratelimit(0, 0)
async def deauth_user(request: app.TypedRequest, conn: asyncpg.Connection):
    data = await request.json()
    usr = data.get("username")

    if request.app.test:
        return web.Response(status=204)

    await conn.fetchrow("UPDATE auths SET active = false WHERE username = $1", usr)
    return web.Response(status=204)

@router.post("/api/internal/users/auth")
@handler.ratelimit(0, 0)
async def auth_user(request: app.TypedRequest, conn: asyncpg.Connection):
    data = await request.json()
    usr = data.get("username")
    if request.app.test:
        return web.Response(status=204)

    await conn.fetchrow("UPDATE auths SET active = true WHERE username = $1", usr)
    return web.Response(status=204)

@router.get("/api/internal/bans")
@handler.ratelimit(0, 0)
async def get_bans(request: app.TypedRequest, conn: asyncpg.Connection):
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
        resp = await conn.fetch("SELECT * FROM bans WHERE ip = $1 AND similarity($2, user_agent) > 0.8 LIMIT 50 OFFSET $3", ip, useragent, offset)
    elif ip:
        resp = await conn.fetch("SELECT * FROM bans WHERE ip = $1 LIMIT 50 OFFSET $2", ip, offset)
    elif useragent:
        resp = await conn.fetch("SELECT * FROM bans WHERE similarity($1, user_agent) > 0.8 LIMIT 50 OFFSET $2", offset)
    else:
        resp = await conn.fetch("SELECT * FROM bans LIMIT 50 OFFSET $1", offset)

    return web.json_response({"bans": [dict(x) for x in resp]})

@router.post("/api/internal/bans")
@handler.ratelimit(0, 0)
async def create_ban(request: app.TypedRequest, conn: asyncpg.Connection):
    ip = request.query.get("ip")
    useragent = request.query.get("user-agent")
    reason = request.query.get("reason")
    if not ip:
        return web.Response(status=400, reason="Missing ip parameter")

    await conn.fetchrow("INSERT INTO bans (ip, user_agent, reason) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING", ip, useragent, reason)
    return web.Response(status=201)

@router.get("/api/internal/logs")
@handler.ratelimit(0, 0)
async def get_logs(request: app.TypedRequest, conn: asyncpg.Connection):
    try:
        page = int(request.query.get("page", "0"))
    except:
        return web.Response(reason="page must be a number", status=400)

    oldest_first = request.query.get("oldest-first", "").lower() == "true"
    safe = request.query.get("safe", "").lower() == "true"

    data = await conn.fetch(f"SELECT endpoint, remote, authorized_user, response_code, accessed, user_agent "
                            f"FROM logs ORDER BY accessed {'ASC' if oldest_first else 'DESC'} OFFSET $1 LIMIT 50;",
                            page*50)
    def hook(row):
        d = dict(row)
        if safe:
            del d['remote']

        for a, b in d.items():
            if isinstance(b, datetime.datetime):
                d[a] = b.isoformat()
        return d

    return web.json_response({"rows": [hook(x) for x in data]})