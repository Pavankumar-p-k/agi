-- core/cloud/migrations/001_init.sql
-- Run once against your Supabase project via the SQL Editor or CLI:
--   supabase db push  OR  paste into Supabase SQL Editor

-- ============================================================
-- Extensions
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- for full-text search

-- ============================================================
-- Tables
-- ============================================================

-- 1. Memories (key-value store)
CREATE TABLE IF NOT EXISTS jarvis_memories (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     text NOT NULL,
    key         text NOT NULL,
    value       jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, key)
);
CREATE INDEX IF NOT EXISTS idx_jarvis_memories_user_key ON jarvis_memories (user_id, key);
CREATE INDEX IF NOT EXISTS idx_jarvis_memories_value_gin ON jarvis_memories USING gin (value);

-- 2. Conversations
CREATE TABLE IF NOT EXISTS jarvis_conversations (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     text NOT NULL,
    messages    jsonb NOT NULL DEFAULT '[]',
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jarvis_conv_user ON jarvis_conversations (user_id);

-- 3. Goals / Projects
CREATE TABLE IF NOT EXISTS jarvis_goals (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     text NOT NULL,
    name        text NOT NULL DEFAULT 'Untitled',
    description text NOT NULL DEFAULT '',
    goal        text NOT NULL DEFAULT '',
    status      text NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'paused', 'completed', 'cancelled')),
    steps       jsonb NOT NULL DEFAULT '[]',
    metadata    jsonb NOT NULL DEFAULT '{}',
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jarvis_goals_user_status ON jarvis_goals (user_id, status);

-- 4. Plugin settings (cloud-synced)
CREATE TABLE IF NOT EXISTS jarvis_plugins_settings (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     text NOT NULL,
    plugin_id   text NOT NULL,
    settings    jsonb NOT NULL DEFAULT '{}',
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, plugin_id)
);

-- ============================================================
-- Auto-update updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ BEGIN
    CREATE TRIGGER trg_memories_updated BEFORE UPDATE ON jarvis_memories
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_goals_updated BEFORE UPDATE ON jarvis_goals
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TRIGGER trg_plugin_settings_updated BEFORE UPDATE ON jarvis_plugins_settings
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ============================================================
-- Row Level Security
-- ============================================================
ALTER TABLE jarvis_memories          ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis_conversations     ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis_goals             ENABLE ROW LEVEL SECURITY;
ALTER TABLE jarvis_plugins_settings  ENABLE ROW LEVEL SECURITY;

-- Policy: users can only see/modify their own rows.
-- Replace auth.uid()::text with your user_id strategy if not using Supabase Auth.

CREATE POLICY memories_self ON jarvis_memories
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY conversations_self ON jarvis_conversations
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY goals_self ON jarvis_goals
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);

CREATE POLICY plugin_settings_self ON jarvis_plugins_settings
    USING (user_id = auth.uid()::text)
    WITH CHECK (user_id = auth.uid()::text);
