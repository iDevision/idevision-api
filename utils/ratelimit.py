import math
from typing import Tuple, Optional

from aiohttp import web
from discord.ext.commands import CooldownMapping, BucketType, Cooldown

import utils.utils as utils

class Bucket2(BucketType):
    pass

class Mapping(CooldownMapping):
    def get_bucket(self, request, current=None):
        self._verify_cache_integrity(current)
        #if request.remote == "127.0.0.1":
        #    return None

        key = self._bucket_key(request)
        if key not in self._cache:
            bucket = self._cooldown.copy()
            self._cache[key] = bucket
        else:
            bucket = self._cache[key]

        return bucket

    def _bucket_key(self, request):
        if self._cooldown.type is Bucket2.default:
            return request.remote
        elif self._cooldown.type is Bucket2.user:
            return request.username
        else:
            raise ValueError

    def update_rate_limit(self, request, current=None) -> Tuple[Optional[float], Optional[Cooldown]]:
        bucket: Cooldown = self.get_bucket(request, current)
        if bucket:
            return bucket.update_rate_limit(current), bucket

        return None, None

_DEFAULT_DICT = {
    'reason': None,
    "username": None,
    "ignores_ratelimits": False,
    "active": None,
    "administrator": False,
    "permissions": {}
}

class Ratelimiter:
    __slots__ = "rate", "per", "ignore_perm", "cb", "map", "autoban", "auth_map", "auth_autoban", "ignore_logging"
    def __init__(self, rate: int, per: int, callback, ignore_perms: str=None, ignore_logging=False):
        self.rate = rate
        self.per = per
        self.ignore_logging = ignore_logging
        self.ignore_perm = ignore_perms
        self.cb = callback
        self.map = Mapping.from_cooldown(rate, per, Bucket2.default)
        self.autoban = Mapping.from_cooldown(rate*2, per, Bucket2.default)
        self.auth_map = Mapping.from_cooldown(rate*2, per, Bucket2.user)
        self.auth_autoban = Mapping.from_cooldown((rate*2)*2, per, Bucket2.user)

    def __call__(self, request: utils.TypedRequest):
        return self._wrap_call(request)

    async def _wrap_call(self, request: utils.TypedRequest):
        async with request.app.db.acquire() as conn:
            request.conn = conn
            resp, login, did_ban = await self.do_call(request, conn)
            if not self.ignore_logging and (did_ban or resp.status != 403):
                await conn.execute(
                    "INSERT INTO logs VALUES ($1, (now() at time zone 'utc'), $2, $3, $4, $5)",
                    request.headers.get("X-Forwarded-For") or request.remote,
                    request.headers.get("User-Agent", "!!Not given!!"),
                    request.path,
                    login,
                    403 if did_ban else resp.status
                )
            return resp

    async def do_call(self, request: utils.TypedRequest, conn):
        ip = request.headers.get("X-Forwarded-For") or request.remote
        # cant do this in 1 query :/
        data = await conn.fetchrow("SELECT reason FROM bans WHERE ip = $1", ip)
        data = dict(data) if data else _DEFAULT_DICT

        if data['reason']:
            return web.Response(status=403, reason=data['reason']), None, False

        _d = await conn.fetchrow("SELECT * FROM auths WHERE auth_key = $1", request.headers.get("Authorization"))
        request.user = _d
        _d = dict(_d) if _d else {}
        data.update(_d)

        if data['active'] is False:
            return web.Response(status=403, reason="Account is disabled"), None, False

        authorized = data['active']
        bucket = d = None

        request.username = data['username']

        high_map, low_map = self.autoban, self.map
        if authorized and data['ignores_ratelimits'] is not True and not data['administrator']:
            low_map.update_rate_limit(request)
            high_map.update_rate_limit(request) # track these still to track ips and whatnot, in case they stop using a token

            high_map, low_map = self.auth_autoban, self.auth_map

        if not data['ignores_ratelimits'] and not data['administrator'] and self.ignore_perm not in data['permissions']:
            ban, _ = high_map.update_rate_limit(request)
            if ban is not None:
                if authorized:
                    await conn.execute("UPDATE auths SET active = false WHERE username = $1", data['username'])

                await conn.execute(
                    "INSERT INTO bans (ip, user_agent, reason) VALUES ($1, $2, 'Auto-ban from api spam') ON CONFLICT DO NOTHING;",
                    ip, request.headers.get("user-agent"))
                return web.Response(status=403, reason="Auto-ban from api spam"), None, True

            d, bucket = low_map.update_rate_limit(request)

        if d:
            response = web.Response(status=429, reason="Too Many Requests")
        else:
            response = await self.cb(request, conn)

        if bucket:
            headers = {
                "ratelimit-remaining": bucket.get_tokens(),
                "ratelimit-max": bucket.rate,
                "ratelimit-reset": round(bucket._window + bucket.per),
                "ratelimit-retry-after": math.ceil(bucket.get_retry_after())
            }
        else:
            headers = {
                "ratelimit-remaining": 1,
                "ratelimit-max": 1,
                "ratelimit-reset": 0,
                "ratelimit-retry-after": 0
            }
        response.headers.update({x: str(y) for x, y in headers.items()})
        return response, data['username'] if data else None, False

def ratelimit(rate: int, per: int, ignore_perm: str=None, ignore_logging=False):
    def wrapped(func):
        return Ratelimiter(rate, per, func, ignore_perm, ignore_logging)
    return wrapped