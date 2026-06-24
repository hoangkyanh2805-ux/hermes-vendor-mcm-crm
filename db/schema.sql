-- MCM Vendor — Hermes XAUUSD Growth OS v2
-- Phase 0: Supabase/Postgres source of truth
-- Run: psql $DATABASE_URL -f db/schema.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- CRM stages (reference)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crm_stages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL UNIQUE,
    sort_order      INTEGER NOT NULL,
    description     TEXT,
    is_terminal     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- X accounts
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS x_accounts (
    id              TEXT PRIMARY KEY,
    handle          TEXT NOT NULL,
    display_name    TEXT,
    country_target  TEXT,
    vendor_id       UUID,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'paused', 'archived')),
    notes           TEXT,
    raw_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_x_accounts_vendor ON x_accounts (vendor_id);
CREATE INDEX IF NOT EXISTS idx_x_accounts_country ON x_accounts (country_target);

-- ---------------------------------------------------------------------------
-- Vendors
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    telegram_handle TEXT,
    email           TEXT,
    country_focus   TEXT,
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'inactive', 'archived')),
    notes           TEXT,
    raw_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- FK from x_accounts to vendors (deferred until vendors exists)
ALTER TABLE x_accounts
    DROP CONSTRAINT IF EXISTS fk_x_accounts_vendor;
ALTER TABLE x_accounts
    ADD CONSTRAINT fk_x_accounts_vendor
    FOREIGN KEY (vendor_id) REFERENCES vendors (id) ON DELETE SET NULL;

-- ---------------------------------------------------------------------------
-- Campaigns
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS campaigns (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    x_account_id    TEXT REFERENCES x_accounts (id) ON DELETE SET NULL,
    vendor_id       UUID REFERENCES vendors (id) ON DELETE SET NULL,
    country_target  TEXT,
    utm_source      TEXT,
    utm_medium      TEXT,
    utm_campaign    TEXT,
    budget_usd      NUMERIC(12, 2),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived')),
    starts_at       TIMESTAMPTZ,
    ends_at         TIMESTAMPTZ,
    raw_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campaigns_x_account ON campaigns (x_account_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_vendor ON campaigns (vendor_id);

-- ---------------------------------------------------------------------------
-- Leads (core attribution entity)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_account      TEXT REFERENCES x_accounts (id) ON DELETE SET NULL,
    source_platform     TEXT NOT NULL DEFAULT 'telegram',
    country_target      TEXT,
    campaign_id         TEXT REFERENCES campaigns (id) ON DELETE SET NULL,
    vendor_id           UUID REFERENCES vendors (id) ON DELETE SET NULL,
    telegram_user_id    BIGINT NOT NULL,
    telegram_username   TEXT,
    join_time           TIMESTAMPTZ,
    current_stage       TEXT NOT NULL DEFAULT 'New X Visitor',
    stage_updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lead_score          NUMERIC(5, 2) NOT NULL DEFAULT 0,
    engagement_score    NUMERIC(5, 2) NOT NULL DEFAULT 0,
    content_angle       TEXT,
    content_id          TEXT,
    paid_flag           BOOLEAN NOT NULL DEFAULT FALSE,
    inactive_days       INTEGER NOT NULL DEFAULT 0,
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_leads_telegram_user UNIQUE (telegram_user_id),
    CONSTRAINT fk_leads_current_stage
        FOREIGN KEY (current_stage) REFERENCES crm_stages (name) ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_leads_campaign ON leads (campaign_id);
CREATE INDEX IF NOT EXISTS idx_leads_vendor ON leads (vendor_id);
CREATE INDEX IF NOT EXISTS idx_leads_country ON leads (country_target);
CREATE INDEX IF NOT EXISTS idx_leads_stage ON leads (current_stage);
CREATE INDEX IF NOT EXISTS idx_leads_join_time ON leads (join_time);

-- ---------------------------------------------------------------------------
-- Telegram joins (capture events)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS telegram_joins (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID REFERENCES leads (id) ON DELETE SET NULL,
    telegram_user_id    BIGINT NOT NULL,
    telegram_username   TEXT,
    start_payload       TEXT,
    source_account      TEXT,
    source_platform     TEXT NOT NULL DEFAULT 'telegram',
    country_target      TEXT,
    campaign_id         TEXT,
    content_id          TEXT,
    join_time           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_duplicate        BOOLEAN NOT NULL DEFAULT FALSE,
    parse_status        TEXT NOT NULL DEFAULT 'ok'
                        CHECK (parse_status IN (
                            'ok', 'missing_payload', 'invalid',
                            'unknown_source', 'unknown_country', 'error'
                        )),
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_telegram_joins_user ON telegram_joins (telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_telegram_joins_lead ON telegram_joins (lead_id);
CREATE INDEX IF NOT EXISTS idx_telegram_joins_join_time ON telegram_joins (join_time);
CREATE INDEX IF NOT EXISTS idx_telegram_joins_campaign ON telegram_joins (campaign_id);

-- ---------------------------------------------------------------------------
-- Members (qualified / active community members)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS members (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID NOT NULL UNIQUE REFERENCES leads (id) ON DELETE CASCADE,
    source_account      TEXT,
    source_platform     TEXT NOT NULL DEFAULT 'telegram',
    country_target      TEXT,
    campaign_id         TEXT,
    vendor_id           UUID REFERENCES vendors (id) ON DELETE SET NULL,
    telegram_user_id    BIGINT NOT NULL UNIQUE,
    telegram_username   TEXT,
    join_time           TIMESTAMPTZ,
    current_stage       TEXT NOT NULL DEFAULT 'Warm Member',
    stage_updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    lead_score          NUMERIC(5, 2) NOT NULL DEFAULT 0,
    engagement_score    NUMERIC(5, 2) NOT NULL DEFAULT 0,
    content_angle       TEXT,
    last_active_at      TIMESTAMPTZ,
    paid_flag           BOOLEAN NOT NULL DEFAULT FALSE,
    left_group          BOOLEAN NOT NULL DEFAULT FALSE,
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_members_current_stage
        FOREIGN KEY (current_stage) REFERENCES crm_stages (name) ON UPDATE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_members_stage ON members (current_stage);
CREATE INDEX IF NOT EXISTS idx_members_last_active ON members (last_active_at);

-- ---------------------------------------------------------------------------
-- Affiliate profiles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS affiliate_profiles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id         UUID REFERENCES leads (id) ON DELETE SET NULL,
    member_id       UUID REFERENCES members (id) ON DELETE SET NULL,
    affiliate_code  TEXT UNIQUE,
    tier            TEXT NOT NULL DEFAULT 'standard',
    commission_rate NUMERIC(5, 2),
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'active', 'suspended', 'churned')),
    country_target  TEXT,
    notes           TEXT,
    raw_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Content assets
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_assets (
    id              TEXT PRIMARY KEY,
    title           TEXT,
    hook            TEXT,
    angle           TEXT,
    hashtag         TEXT,
    country_target  TEXT,
    x_account_id    TEXT REFERENCES x_accounts (id) ON DELETE SET NULL,
    vendor_id       UUID REFERENCES vendors (id) ON DELETE SET NULL,
    campaign_id     TEXT REFERENCES campaigns (id) ON DELETE SET NULL,
    source_post_url TEXT,
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'assigned', 'posted', 'tracked', 'winning', 'failed', 'archived')),
    notes           TEXT,
    raw_payload     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Content performance
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS content_performance (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content_id          TEXT NOT NULL REFERENCES content_assets (id) ON DELETE CASCADE,
    source_post_url     TEXT,
    x_account_id        TEXT REFERENCES x_accounts (id) ON DELETE SET NULL,
    vendor_id           UUID REFERENCES vendors (id) ON DELETE SET NULL,
    country_target      TEXT,
    campaign_id         TEXT REFERENCES campaigns (id) ON DELETE SET NULL,
    hook                TEXT,
    angle               TEXT,
    hashtag             TEXT,
    post_url            TEXT,
    posted_at           TIMESTAMPTZ,
    views               BIGINT NOT NULL DEFAULT 0,
    likes               BIGINT NOT NULL DEFAULT 0,
    replies             BIGINT NOT NULL DEFAULT 0,
    reposts             BIGINT NOT NULL DEFAULT 0,
    clicks              BIGINT NOT NULL DEFAULT 0,
    telegram_joins      INTEGER NOT NULL DEFAULT 0,
    join_rate           NUMERIC(8, 4) GENERATED ALWAYS AS (
        CASE WHEN clicks > 0 THEN telegram_joins::NUMERIC / clicks ELSE 0 END
    ) STORED,
    status              TEXT NOT NULL DEFAULT 'draft'
                        CHECK (status IN ('draft', 'assigned', 'posted', 'tracked', 'winning', 'failed', 'archived')),
    notes               TEXT,
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_perf_content ON content_performance (content_id);
CREATE INDEX IF NOT EXISTS idx_content_perf_status ON content_performance (status);
CREATE INDEX IF NOT EXISTS idx_content_perf_campaign ON content_performance (campaign_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_perf_content_id ON content_performance (content_id);

-- ---------------------------------------------------------------------------
-- Apify posts (normalized crawl output)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS apify_posts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform            TEXT NOT NULL DEFAULT 'x',
    query               TEXT,
    country_target      TEXT,
    hashtag             TEXT,
    post_url            TEXT,
    post_text           TEXT,
    author_handle       TEXT,
    author_name         TEXT,
    author_followers    BIGINT,
    created_at_post     TIMESTAMPTZ,
    likes               BIGINT NOT NULL DEFAULT 0,
    replies             BIGINT NOT NULL DEFAULT 0,
    reposts             BIGINT NOT NULL DEFAULT 0,
    views               BIGINT NOT NULL DEFAULT 0,
    engagement_score    NUMERIC(10, 2) NOT NULL DEFAULT 0,
    category            TEXT
                        CHECK (category IN ('signal', 'proof', 'education', 'promo', 'noise', NULL)),
    lead_potential      TEXT
                        CHECK (lead_potential IN ('High', 'Medium', 'Low', NULL)),
    hook_extracted      TEXT,
    content_angle       TEXT,
    action              TEXT,
    crawl_run_id        TEXT,
    raw_json            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_apify_posts_country ON apify_posts (country_target);
CREATE INDEX IF NOT EXISTS idx_apify_posts_hashtag ON apify_posts (hashtag);
CREATE INDEX IF NOT EXISTS idx_apify_posts_potential ON apify_posts (lead_potential);

-- ---------------------------------------------------------------------------
-- Country intelligence (daily aggregates)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS country_intelligence (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_date         DATE NOT NULL,
    country_target      TEXT NOT NULL,
    top_hashtag         TEXT,
    top_hook            TEXT,
    top_author          TEXT,
    top_content_angle   TEXT,
    posts_crawled       INTEGER NOT NULL DEFAULT 0,
    high_potential_count INTEGER NOT NULL DEFAULT 0,
    noise_warning       TEXT,
    vendor_task_suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    posts_to_rewrite    JSONB NOT NULL DEFAULT '[]'::jsonb,
    posts_to_seed       JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_country_intel_date_country UNIQUE (report_date, country_target)
);

-- ---------------------------------------------------------------------------
-- Vendor tasks (Plane sync target)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vendor_tasks (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plane_task_id       TEXT,
    title               TEXT NOT NULL,
    description         TEXT,
    country_target      TEXT,
    hashtag             TEXT,
    angle               TEXT,
    hook                TEXT,
    source_post_url     TEXT,
    vendor_id           UUID REFERENCES vendors (id) ON DELETE SET NULL,
    content_id          TEXT REFERENCES content_assets (id) ON DELETE SET NULL,
    status              TEXT NOT NULL DEFAULT 'backlog'
                        CHECK (status IN (
                            'backlog', 'ready_to_post', 'assigned', 'posted',
                            'need_fix', 'winning', 'archived', 'overdue'
                        )),
    deadline            TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vendor_tasks_status ON vendor_tasks (status);
CREATE INDEX IF NOT EXISTS idx_vendor_tasks_plane ON vendor_tasks (plane_task_id);

-- ---------------------------------------------------------------------------
-- CRM stage events
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS crm_stage_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id             UUID REFERENCES leads (id) ON DELETE CASCADE,
    member_id           UUID REFERENCES members (id) ON DELETE SET NULL,
    from_stage          TEXT,
    to_stage            TEXT NOT NULL,
    reason              TEXT,
    triggered_by        TEXT NOT NULL DEFAULT 'system',
    twenty_synced       BOOLEAN NOT NULL DEFAULT FALSE,
    twenty_sync_error   TEXT,
    raw_payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crm_stage_events_lead ON crm_stage_events (lead_id);
CREATE INDEX IF NOT EXISTS idx_crm_stage_events_created ON crm_stage_events (created_at);

-- ---------------------------------------------------------------------------
-- Activity logs (audit trail)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type         TEXT NOT NULL,
    entity_id           TEXT,
    action              TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'success'
                        CHECK (status IN ('success', 'failure', 'warning', 'info')),
    message             TEXT,
    actor               TEXT NOT NULL DEFAULT 'system',
    source              TEXT,
    error_detail        TEXT,
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_logs_entity ON activity_logs (entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs (created_at);
CREATE INDEX IF NOT EXISTS idx_activity_logs_status ON activity_logs (status);

-- ---------------------------------------------------------------------------
-- Daily KPIs (rollup for founder report / Metabase)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS daily_kpis (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kpi_date                DATE NOT NULL UNIQUE,
    telegram_joins          INTEGER NOT NULL DEFAULT 0,
    top_country             TEXT,
    top_x_account           TEXT,
    top_vendor              TEXT,
    cost_per_join           NUMERIC(12, 4),
    new_x_visitor           INTEGER NOT NULL DEFAULT 0,
    telegram_joined         INTEGER NOT NULL DEFAULT 0,
    warm_member             INTEGER NOT NULL DEFAULT 0,
    signal_interested       INTEGER NOT NULL DEFAULT 0,
    paid_vip                INTEGER NOT NULL DEFAULT 0,
    renewal_risk            INTEGER NOT NULL DEFAULT 0,
    posts_tracked           INTEGER NOT NULL DEFAULT 0,
    winning_hook            TEXT,
    top_hashtag             TEXT,
    best_content_angle      TEXT,
    apify_run_status        TEXT,
    apify_posts_crawled     INTEGER NOT NULL DEFAULT 0,
    apify_high_potential    INTEGER NOT NULL DEFAULT 0,
    vendor_tasks_created    INTEGER NOT NULL DEFAULT 0,
    vendor_tasks_posted     INTEGER NOT NULL DEFAULT 0,
    vendor_tasks_overdue    INTEGER NOT NULL DEFAULT 0,
    raw_payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- System health logs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS system_health_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name        TEXT NOT NULL,
    status              TEXT NOT NULL
                        CHECK (status IN ('healthy', 'degraded', 'down', 'unknown')),
    latency_ms          INTEGER,
    message             TEXT,
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,
    checked_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_health_service ON system_health_logs (service_name, checked_at DESC);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'crm_stages', 'x_accounts', 'vendors', 'campaigns', 'leads', 'telegram_joins',
        'members', 'affiliate_profiles', 'content_assets', 'content_performance',
        'apify_posts', 'country_intelligence', 'vendor_tasks', 'daily_kpis'
    ]
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_%s_updated_at ON %I', t, t);
        EXECUTE format(
            'CREATE TRIGGER trg_%s_updated_at BEFORE UPDATE ON %I
             FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            t, t
        );
    END LOOP;
END;
$$;

-- ---------------------------------------------------------------------------
-- Activity log helper
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION log_activity(
    p_entity_type TEXT,
    p_entity_id   TEXT,
    p_action      TEXT,
    p_status      TEXT DEFAULT 'success',
    p_message     TEXT DEFAULT NULL,
    p_actor       TEXT DEFAULT 'system',
    p_source      TEXT DEFAULT NULL,
    p_error_detail TEXT DEFAULT NULL,
    p_payload     JSONB DEFAULT '{}'::jsonb
)
RETURNS UUID AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO activity_logs (
        entity_type, entity_id, action, status, message,
        actor, source, error_detail, payload
    ) VALUES (
        p_entity_type, p_entity_id, p_action, p_status, p_message,
        p_actor, p_source, p_error_detail, p_payload
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Auto-log lead insert/update
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_leads_activity()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM log_activity(
            'leads', NEW.id::TEXT, 'insert', 'success',
            'Lead created', 'trigger', 'db',
            NULL, jsonb_build_object('telegram_user_id', NEW.telegram_user_id, 'stage', NEW.current_stage)
        );
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM log_activity(
            'leads', NEW.id::TEXT, 'update', 'success',
            'Lead updated', 'trigger', 'db',
            NULL, jsonb_build_object(
                'old_stage', OLD.current_stage,
                'new_stage', NEW.current_stage,
                'telegram_user_id', NEW.telegram_user_id
            )
        );
        IF OLD.current_stage IS DISTINCT FROM NEW.current_stage THEN
            INSERT INTO crm_stage_events (lead_id, from_stage, to_stage, reason, triggered_by)
            VALUES (NEW.id, OLD.current_stage, NEW.current_stage, 'stage_change', 'trigger');
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_leads_activity ON leads;
CREATE TRIGGER trg_leads_activity
    AFTER INSERT OR UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION trg_leads_activity();

-- ---------------------------------------------------------------------------
-- Auto-log telegram_joins insert/update
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_telegram_joins_activity()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        PERFORM log_activity(
            'telegram_joins', NEW.id::TEXT, 'insert', 'success',
            'Telegram join captured', 'trigger', 'db',
            NULL, jsonb_build_object('telegram_user_id', NEW.telegram_user_id, 'parse_status', NEW.parse_status)
        );
    ELSIF TG_OP = 'UPDATE' THEN
        PERFORM log_activity(
            'telegram_joins', NEW.id::TEXT, 'update', 'success',
            'Telegram join updated', 'trigger', 'db',
            NULL, jsonb_build_object('is_duplicate', NEW.is_duplicate, 'parse_status', NEW.parse_status)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_telegram_joins_activity ON telegram_joins;
CREATE TRIGGER trg_telegram_joins_activity
    AFTER INSERT OR UPDATE ON telegram_joins
    FOR EACH ROW EXECUTE FUNCTION trg_telegram_joins_activity();

-- ---------------------------------------------------------------------------
-- Phase 5: Sync content_assets when performance marked winning
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trg_content_performance_winning()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'winning' AND (OLD.status IS DISTINCT FROM 'winning') THEN
        UPDATE content_assets SET status = 'winning', updated_at = NOW()
        WHERE id = NEW.content_id;
        PERFORM log_activity(
            'content_performance', NEW.id::TEXT, 'mark_winning', 'success',
            'Content marked winning', 'trigger', 'db',
            NULL, jsonb_build_object('content_id', NEW.content_id, 'join_rate', NEW.join_rate)
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_content_performance_winning ON content_performance;
CREATE TRIGGER trg_content_performance_winning
    AFTER UPDATE OF status ON content_performance
    FOR EACH ROW EXECUTE FUNCTION trg_content_performance_winning();
