-- PhotoFlow v2 schema migration
-- Run once on live DB: psql $DATABASE_URL -f migrate_v2.sql

-- ── Photos: new columns ───────────────────────────────────────────────────────
ALTER TABLE photos
    ADD COLUMN IF NOT EXISTS taken_at_original    VARCHAR(32),
    ADD COLUMN IF NOT EXISTS timezone_offset       VARCHAR(8),
    ADD COLUMN IF NOT EXISTS orientation           INTEGER,
    ADD COLUMN IF NOT EXISTS color_space           VARCHAR(32),
    ADD COLUMN IF NOT EXISTS camera_serial         VARCHAR(128),
    ADD COLUMN IF NOT EXISTS lens_make             VARCHAR(128),
    ADD COLUMN IF NOT EXISTS focal_length_35mm     INTEGER,
    ADD COLUMN IF NOT EXISTS exposure_time         FLOAT,
    ADD COLUMN IF NOT EXISTS exposure_mode         VARCHAR(64),
    ADD COLUMN IF NOT EXISTS metering_mode         INTEGER,
    ADD COLUMN IF NOT EXISTS white_balance         INTEGER,
    ADD COLUMN IF NOT EXISTS flash                 INTEGER,
    ADD COLUMN IF NOT EXISTS software              VARCHAR(256),
    ADD COLUMN IF NOT EXISTS gps_accuracy          FLOAT,
    ADD COLUMN IF NOT EXISTS country_code          VARCHAR(4),
    ADD COLUMN IF NOT EXISTS artist                VARCHAR(256),
    ADD COLUMN IF NOT EXISTS copyright             VARCHAR(512),
    ADD COLUMN IF NOT EXISTS title                 VARCHAR(512),
    ADD COLUMN IF NOT EXISTS caption               TEXT,
    ADD COLUMN IF NOT EXISTS keywords              TEXT,
    ADD COLUMN IF NOT EXISTS xmp_sidecar_written   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS xmp_sidecar_path      VARCHAR(2048),
    ADD COLUMN IF NOT EXISTS description_model     VARCHAR(128),
    ADD COLUMN IF NOT EXISTS video_fps             FLOAT,
    ADD COLUMN IF NOT EXISTS video_bitrate         INTEGER,
    ADD COLUMN IF NOT EXISTS user_description      TEXT;

-- ── Albums: extend for smart/ai types ────────────────────────────────────────
-- Create enum if not exists (PostgreSQL doesn't have CREATE TYPE IF NOT EXISTS)
DO $$ BEGIN
    CREATE TYPE albumtype AS ENUM ('manual', 'smart', 'ai');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE albums
    ADD COLUMN IF NOT EXISTS album_type        albumtype NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS smart_criteria    JSONB,
    ADD COLUMN IF NOT EXISTS ai_prompt         TEXT,
    ADD COLUMN IF NOT EXISTS ai_last_evaluated TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at        TIMESTAMPTZ DEFAULT NOW();

ALTER TABLE album_photos
    ADD COLUMN IF NOT EXISTS ai_score FLOAT;

-- ── Persons: alias column ────────────────────────────────────────────────────
ALTER TABLE persons
    ADD COLUMN IF NOT EXISTS alias VARCHAR(256);

DO $$ BEGIN RAISE NOTICE 'Migration v2 complete.'; END $$;
