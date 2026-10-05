CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE TABLE IF NOT EXISTS outbox (
 id UUID PRIMARY KEY, event JSONB NOT NULL, sent BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS inbox (id UUID PRIMARY KEY);
CREATE TABLE IF NOT EXISTS resources (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, data JSONB NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, role TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE TABLE IF NOT EXISTS bookings (
 id UUID PRIMARY KEY, user_id TEXT NOT NULL, resource_id TEXT NOT NULL,
 starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('confirmed','cancelled')),
 request_key TEXT NOT NULL, request_body JSONB NOT NULL,
 UNIQUE(user_id, request_key), CHECK(starts_at < ends_at),
 EXCLUDE USING gist (resource_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
 WHERE (status = 'confirmed')
);
CREATE TABLE IF NOT EXISTS notifications (
 id UUID PRIMARY KEY, user_id TEXT NOT NULL, event JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
