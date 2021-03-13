create extension pg_trgm;
create table auths
(
    username       text primary key,
    auth_key       text,
    allowed_routes text[],
    active         boolean default true not null,
    discord_id     bigint,
    ignores_ratelimits boolean not null default false
);
create table uploads
(
    key      text,
    username text references auths (username) ON DELETE CASCADE,
    time     timestamp,
    views integer not null default 0,
    allowed_authorizations text[],
    location text
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
    restricted boolean not null,
    remote text not null,
    accessed timestamp not null,
    user_agent text not null,
    authorized_user text,
    response_code integer not null
);