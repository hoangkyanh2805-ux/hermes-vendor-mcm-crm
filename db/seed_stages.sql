-- MCM Vendor — Hermes XAUUSD Growth OS v2
-- Phase 0: CRM stage seed data
-- Run after schema.sql: psql $DATABASE_URL -f db/seed_stages.sql

INSERT INTO crm_stages (name, sort_order, description, is_terminal) VALUES
    ('New X Visitor',      1, 'Visitor from X/BioLink before Telegram join', FALSE),
    ('Telegram Joined',    2, 'Joined Telegram via deep link /start', FALSE),
    ('Warm Member',        3, 'Engaged member (clicks, replies)', FALSE),
    ('Signal Interested',  4, 'Asked about VIP, signal, or bot', FALSE),
    ('Trial / Consult',    5, 'Admin marked consult or trial', FALSE),
    ('Paid / VIP',         6, 'Paid or VIP member', FALSE),
    ('Renewal Risk',       7, 'Inactive beyond threshold', FALSE),
    ('Churned',            8, 'Left group or long-term inactive', TRUE)
ON CONFLICT (name) DO UPDATE SET
    sort_order   = EXCLUDED.sort_order,
    description  = EXCLUDED.description,
    is_terminal  = EXCLUDED.is_terminal,
    updated_at   = NOW();

-- Demo reference data for Phase 0 acceptance test (optional)
INSERT INTO vendors (code, name, country_focus, status) VALUES
    ('vendor_demo', 'Demo Vendor', 'UAE', 'active')
ON CONFLICT (code) DO NOTHING;

INSERT INTO x_accounts (id, handle, display_name, country_target, status) VALUES
    ('xacc_uae_001', 'hermes_gold_uae', 'Hermes Gold UAE', 'UAE', 'active')
ON CONFLICT (id) DO NOTHING;

INSERT INTO campaigns (id, name, x_account_id, country_target, status) VALUES
    ('goldhook_20260624', 'Gold Hook June 2026', 'xacc_uae_001', 'UAE', 'active')
ON CONFLICT (id) DO NOTHING;

-- Phase 5: demo content asset for performance tracker tests
INSERT INTO content_assets (
    id, title, hook, angle, hashtag, country_target, x_account_id, campaign_id, status, source_post_url
) VALUES (
    'hook001',
    'UAE Gold Breakout Post',
    'Gold breakout above 2350 — XAUUSD long setup',
    'breakout',
    '#xauusd',
    'uae',
    'xacc_uae_001',
    'goldhook_20260624',
    'draft',
    'https://x.com/hermes_gold_uae/status/demo001'
) ON CONFLICT (id) DO NOTHING;
