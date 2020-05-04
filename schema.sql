create table if not exists uploads (key text, user text, time integer);
create table if not exists auths (username text, authorization text);
create table if not exists bot_data (botname text, ping integer, latency integer, timestamp integer);