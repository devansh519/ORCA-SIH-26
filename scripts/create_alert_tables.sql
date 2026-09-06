CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.frequent_zones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    alert_radius_km DOUBLE PRECISION NOT NULL DEFAULT 1.0 CHECK (alert_radius_km > 0),
    language TEXT NOT NULL DEFAULT 'ta',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_frequent_zones_user_active
    ON public.frequent_zones (user_id, active);

CREATE TABLE IF NOT EXISTS public.proactive_alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    zone_id UUID NOT NULL REFERENCES public.frequent_zones(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('RED', 'AMBER')),
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    boundary_distance_km DOUBLE PRECISION,
    inside_eez BOOLEAN,
    source TEXT NOT NULL,
    source_timestamp TIMESTAMPTZ,
    delivery_status TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proactive_alerts_user_created
    ON public.proactive_alerts (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_proactive_alerts_zone_created
    ON public.proactive_alerts (zone_id, created_at DESC);
