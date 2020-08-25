create table uploads
(
    key      text,
    username text references auths (username) ON DELETE CASCADE,
    time     timestamp
);
create table auths
(
    username       text primary key,
    auth_key       text,
    allowed_routes text [],
    active         boolean default true not null
);
create table bot_data
(
    botname   text references auths (username),
    ping      integer,
    latency   integer,
    timestamp integer
);
create table tinyurls
(
    username text references auths (username) ON DELETE CASCADE,
    link     text,
    url      text
)