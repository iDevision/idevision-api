create extension pg_trgm;
create table slaves (
    node serial primary key,
    name text unique not null,
    ip text not null,
    port integer not null,
    UNIQUE (ip, port)
);
create table auths
(
    username       text primary key,
    auth_key       text,
    permissions     text[],
    active         boolean default true not null,
    discord_id     bigint,
    ignores_ratelimits boolean not null default false
);
create table permissions
(
    name text primary key
);
create table routes
(
    route text not null,
    method text not null,
    PRIMARY KEY (route, method),
    permission text references permissions(name)
);
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
    expiry timestamp without time zone,
    PRIMARY KEY(key, node)
);
create table applications (
    userid  bigint primary key,
    username text not null,
    reason text not null,
    routes text[] not null,
    decline_reason text
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
    reason text,
    expires timestamp without time zone
);
create table logs
(
    remote text not null,
    accessed timestamp not null,
    user_agent text not null,
    endpoint text not null,
    authorized_user text,
    response_code integer not null
);
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
create table rtfm (
    url text primary key,
    expiry timestamp not null default ((now() at time zone 'utc') + INTERVAL '1 week'),
    indexed timestamp not null default (now() at time zone 'utc')
);
create table rtfm_lookup (
    url text not null references rtfm(url) ON DELETE CASCADE,
    key text not null,
    value text not null,
    is_label boolean not null
);
create table xkcd (
    num integer primary key,
    posted timestamp not null,
    safe_title text not null,
    title text not null,
    alt text not null,
    transcript text,
    news text,
    image_url text not null,
    url text not null,
    extra_tags text[] not null default '{}'
)