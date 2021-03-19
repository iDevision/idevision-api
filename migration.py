import asyncio
import asyncpg
import os

async def main():
    conn = await asyncpg.connect("postgres://") # type: asyncpg.Connection
    async with conn.transaction() as trans:
        await conn.execute("alter table auths add column administrator bool not null default false")
        await conn.execute("""
        create table slaves (
    node serial primary key,
    name text unique not null,
    ip text not null,
    port integer not null,
    UNIQUE (ip, port)
);
        """)
        await conn.execute("INSERT INTO slaves VALUES (1, 'migrated', '127.0.0.1', '8350');")
        # move /var/www/idevision/media to slave-location/data
        os.rename("/var/www/idevision/media", "/var/www/idevision/migration-slave/data")

        all_uploads = await conn.fetch("SELECT * FROM uploads")
        await conn.execute("DROP TABLE uploads")
        await conn.execute("""
        create table uploads
(
    key      text not null,
    username text references auths (username) ON DELETE CASCADE,
    time     timestamp,
    views integer not null default 0,
    allowed_authorizations text[],
    location text,
    node integer not null references slaves (node),
    deleted boolean not null default false,
    size bigint,
    PRIMARY KEY(key, node)
);
        """)
        await conn.executemany("INSERT INTO uploads VALUES ($1, $2, $3, $4, $5, $6, 1, false, $7)",
                               [(
                                   x['key'],
                                    x['username'],
                                    x['time'],
                                    x['views'],
                                    x['allowed_authorizations'],
                                    f"media/{x['key']}",
                                    os.stat(f"/var/www/idevision/migration-slave/data/{x['key']}").st_size
                               )
                                for x in all_uploads])
        await conn.execute("drop table if exists cdn_logs;")
        await conn.execute("""
        create table cdn_logs (
    image text not null,
    node integer not null,
    restricted boolean not null,
    remote text not null,
    accessed timestamp not null,
    user_agent text not null,
    authorized_user text,
    response_code integer not null
);
        """)

asyncio.run(main())