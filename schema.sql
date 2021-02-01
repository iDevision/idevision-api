create extension pg_trgm;
create table auths
(
    username       text primary key,
    auth_key       text,
    allowed_routes text[],
    active         boolean default true not null
);
create table uploads
(
    key      text,
    username text references auths (username) ON DELETE CASCADE,
    time     timestamp
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
);
create table homepages
(
    username     text primary key,
    display_name text,
    link1        text default 'https://github.com',
    link1_name   text default 'Github',
    link2        text default 'https://github.com',
    link2_name   text default 'Github',
    link3        text default 'https://github.com',
    link3_name   text default 'Github',
    link4        text default 'https://github.com',
    link4_name   text default 'Github'
);
create table bans
(
    ip text primary key,
    timestamp timestamp not null default (now() at time zone 'utc'),
    user_agent text,
    reason text
);
create table logs
(
    remote text not null,
    accessed timestamp not null,
    user_agent text not null,
    endpoint text not null
);