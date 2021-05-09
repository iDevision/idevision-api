import asyncio
import asyncpg
import os
import json

async def main():
    with open("config.json") as f:
        cfg = json.load(f)
    conn = await asyncpg.connect(cfg['db']) # type: asyncpg.Connection
    betaconn = await asyncpg.connect(cfg['db']+"_beta")
    async with conn.transaction() as trans:
        beta_routes = await betaconn.fetch("SELECT * FROM routes;")
        await conn.executemany("INSERT INTO routes VALUES ($1, $2, $3)", [[x['route'], x['method'], x['permission']] for x in beta_routes])

        users = await conn.fetch("select * from auths;")
        _updates = []
        for user in users:
            new_perms = []
            perms = user['permissions']
            if user['administrator']:
                new_perms.append("administrator")

            if perms.pop("cdn"):
                new_perms.append("cdn.upload")

            new_perms += perms
            _updates.append([user['username'], new_perms])

        await conn.execute("ALTER TABLE auths DROP COLUMN administrator;")
        await conn.executemany("UPDATE auths SET permissions = $2 WHERE username = $1", _updates)


asyncio.run(main())