-- 001_tracking_provenance.sql
-- SitRep tracking + provenance foundation

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS source_systems (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    description TEXT,
    trust_weight NUMERIC DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS observations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    source_system TEXT NOT NULL,
    source_type TEXT NOT NULL,

    object_type TEXT,
    collected_at TIMESTAMPTZ NOT NULL,
    ingested_at TIMESTAMPTZ DEFAULT now(),

    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    altitude_m DOUBLE PRECISION,

    confidence NUMERIC CHECK (confidence >= 0 AND confidence <= 1),

    features JSONB DEFAULT '{}'::jsonb,
    raw_payload JSONB DEFAULT '{}'::jsonb,

    classification_tag TEXT DEFAULT 'UNCLASSIFIED',
    tenant_id TEXT DEFAULT 'default',

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    entity_type TEXT NOT NULL,
    identity_label TEXT DEFAULT 'unknown',
    status TEXT DEFAULT 'active',

    first_seen_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,

    current_latitude DOUBLE PRECISION,
    current_longitude DOUBLE PRECISION,
    current_altitude_m DOUBLE PRECISION,

    current_confidence NUMERIC DEFAULT 0.0,

    tenant_id TEXT DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tracks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,

    status TEXT DEFAULT 'active',
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS track_points (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    track_id UUID NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    observation_id UUID REFERENCES observations(id) ON DELETE SET NULL,

    recorded_at TIMESTAMPTZ NOT NULL,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    altitude_m DOUBLE PRECISION,

    speed_knots DOUBLE PRECISION,
    heading_degrees DOUBLE PRECISION,

    confidence NUMERIC DEFAULT 0.0,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS associations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    observation_id UUID NOT NULL REFERENCES observations(id) ON DELETE CASCADE,
    entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,

    association_score NUMERIC NOT NULL,
    association_reason TEXT,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fusion_outputs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
    assessment TEXT NOT NULL,
    confidence NUMERIC DEFAULT 0.0,
    explanation TEXT,

    evidence JSONB DEFAULT '[]'::jsonb,

    tenant_id TEXT DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provenance_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    output_type TEXT NOT NULL,
    output_id UUID NOT NULL,

    derived_from_observations JSONB DEFAULT '[]'::jsonb,
    processing_steps JSONB DEFAULT '[]'::jsonb,

    policy_context JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS operator_actions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
    observation_id UUID REFERENCES observations(id) ON DELETE SET NULL,
    fusion_output_id UUID REFERENCES fusion_outputs(id) ON DELETE SET NULL,

    action_type TEXT NOT NULL,
    action_note TEXT,
    operator_id TEXT DEFAULT 'operator',

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_observations_time ON observations(collected_at);
CREATE INDEX IF NOT EXISTS idx_observations_location ON observations(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_entities_type_status ON entities(entity_type, status);
CREATE INDEX IF NOT EXISTS idx_track_points_track_time ON track_points(track_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_associations_observation ON associations(observation_id);
CREATE INDEX IF NOT EXISTS idx_associations_entity ON associations(entity_id);
