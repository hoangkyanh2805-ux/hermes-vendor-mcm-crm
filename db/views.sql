-- MCM Vendor — Hermes XAUUSD Growth OS v2
-- Phase 0 + Phase 3: Dashboard and reporting views
-- Run after schema.sql + seed_stages.sql: psql $DATABASE_URL -f db/views.sql

-- ---------------------------------------------------------------------------
-- v_daily_growth — joins and stage movement by day
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_growth AS
SELECT
    DATE(tj.join_time) AS growth_date,
    COUNT(*) AS telegram_joins,
    COUNT(*) FILTER (WHERE tj.parse_status = 'ok') AS attributed_joins,
    COUNT(*) FILTER (WHERE tj.is_duplicate) AS duplicate_joins,
    COUNT(DISTINCT tj.country_target) AS countries_active,
    COUNT(DISTINCT tj.campaign_id) AS campaigns_active
FROM telegram_joins tj
GROUP BY DATE(tj.join_time)
ORDER BY growth_date DESC;

-- ---------------------------------------------------------------------------
-- v_country_performance — joins and leads by country
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_country_performance AS
SELECT
    COALESCE(l.country_target, 'unknown') AS country_target,
    COUNT(DISTINCT l.id) AS total_leads,
    COUNT(DISTINCT l.id) FILTER (WHERE l.current_stage = 'Telegram Joined') AS telegram_joined,
    COUNT(DISTINCT l.id) FILTER (WHERE l.current_stage = 'Paid / VIP') AS paid_vip,
    COUNT(DISTINCT l.id) FILTER (WHERE l.current_stage = 'Churned') AS churned,
    ROUND(AVG(l.engagement_score), 2) AS avg_engagement_score,
    MAX(l.join_time) AS last_join_time
FROM leads l
GROUP BY COALESCE(l.country_target, 'unknown')
ORDER BY total_leads DESC;

-- ---------------------------------------------------------------------------
-- v_vendor_performance — vendor attribution rollup
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_vendor_performance AS
SELECT
    v.id AS vendor_id,
    v.code AS vendor_code,
    v.name AS vendor_name,
    COUNT(DISTINCT l.id) AS total_leads,
    COUNT(DISTINCT l.id) FILTER (WHERE l.current_stage IN ('Paid / VIP', 'Trial / Consult')) AS converted_leads,
    COUNT(DISTINCT vt.id) AS total_tasks,
    COUNT(DISTINCT vt.id) FILTER (WHERE vt.status = 'overdue') AS overdue_tasks,
    COUNT(DISTINCT cp.id) FILTER (WHERE cp.status = 'winning') AS winning_content_count
FROM vendors v
LEFT JOIN leads l ON l.vendor_id = v.id
LEFT JOIN vendor_tasks vt ON vt.vendor_id = v.id
LEFT JOIN content_performance cp ON cp.vendor_id = v.id
GROUP BY v.id, v.code, v.name
ORDER BY total_leads DESC;

-- ---------------------------------------------------------------------------
-- v_content_performance — content metrics with join attribution (Phase 5)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_content_performance AS
SELECT
    cp.id,
    cp.content_id,
    cp.source_post_url,
    cp.x_account_id,
    cp.vendor_id,
    cp.country_target,
    cp.campaign_id,
    cp.hook,
    cp.angle,
    cp.hashtag,
    cp.post_url,
    cp.posted_at,
    cp.views,
    cp.likes,
    cp.replies,
    cp.reposts,
    cp.clicks,
    cp.telegram_joins,
    cp.join_rate,
    cp.status,
    cp.notes,
    ca.title AS content_title,
    xa.handle AS x_account_handle,
    v.name AS vendor_name,
    c.name AS campaign_name,
    CASE
        WHEN cp.join_rate >= 0.10 THEN 'excellent'
        WHEN cp.join_rate >= 0.05 THEN 'good'
        WHEN cp.join_rate > 0 THEN 'fair'
        ELSE 'no_joins'
    END AS performance_tier,
    CASE WHEN cp.status = 'winning' THEN TRUE ELSE FALSE END AS is_winning
FROM content_performance cp
LEFT JOIN content_assets ca ON ca.id = cp.content_id
LEFT JOIN x_accounts xa ON xa.id = cp.x_account_id
LEFT JOIN vendors v ON v.id = cp.vendor_id
LEFT JOIN campaigns c ON c.id = cp.campaign_id
ORDER BY cp.telegram_joins DESC, cp.join_rate DESC;

-- ---------------------------------------------------------------------------
-- v_winning_content — reusable winning hooks/angles for repurpose
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_winning_content AS
SELECT
    cp.content_id,
    cp.hook,
    cp.angle,
    cp.hashtag,
    cp.country_target,
    cp.campaign_id,
    cp.post_url,
    cp.telegram_joins,
    cp.clicks,
    cp.join_rate,
    cp.posted_at,
    xa.handle AS x_account_handle,
    v.name AS vendor_name,
    ca.source_post_url
FROM content_performance cp
JOIN content_assets ca ON ca.id = cp.content_id
LEFT JOIN x_accounts xa ON xa.id = cp.x_account_id
LEFT JOIN vendors v ON v.id = cp.vendor_id
WHERE cp.status = 'winning' OR ca.status = 'winning'
ORDER BY cp.join_rate DESC, cp.telegram_joins DESC;

-- ---------------------------------------------------------------------------
-- v_content_status_summary — pipeline counts by content status
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_content_status_summary AS
SELECT
    status,
    COUNT(*) AS content_count,
    SUM(telegram_joins) AS total_joins,
    SUM(clicks) AS total_clicks,
    ROUND(AVG(join_rate), 4) AS avg_join_rate
FROM content_performance
GROUP BY status
ORDER BY
    CASE status
        WHEN 'draft' THEN 1
        WHEN 'assigned' THEN 2
        WHEN 'posted' THEN 3
        WHEN 'tracked' THEN 4
        WHEN 'winning' THEN 5
        WHEN 'failed' THEN 6
        WHEN 'archived' THEN 7
        ELSE 8
    END;

-- ---------------------------------------------------------------------------
-- v_crm_stage_funnel — stage counts and average age
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_crm_stage_funnel AS
SELECT
    cs.name AS stage_name,
    cs.sort_order,
    COUNT(l.id) AS lead_count,
    ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - l.stage_updated_at)) / 86400), 1) AS avg_days_in_stage,
    COUNT(l.id) FILTER (WHERE l.stage_updated_at < NOW() - INTERVAL '3 days') AS stale_count
FROM crm_stages cs
LEFT JOIN leads l ON l.current_stage = cs.name
GROUP BY cs.name, cs.sort_order
ORDER BY cs.sort_order;

-- ---------------------------------------------------------------------------
-- v_purgatory_dashboard — stuck leads, inactive members, overdue ops
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_purgatory_dashboard AS
SELECT
    'stuck_stage' AS alert_type,
    l.id::TEXT AS entity_id,
    l.telegram_username AS label,
    l.current_stage AS detail,
    EXTRACT(DAY FROM NOW() - l.stage_updated_at)::INTEGER AS days_stuck,
    l.country_target
FROM leads l
WHERE l.stage_updated_at < NOW() - INTERVAL '7 days'
  AND l.current_stage NOT IN ('Paid / VIP', 'Churned')

UNION ALL

SELECT
    'inactive_member' AS alert_type,
    m.id::TEXT,
    m.telegram_username,
    m.current_stage,
    EXTRACT(DAY FROM NOW() - COALESCE(m.last_active_at, m.join_time))::INTEGER,
    m.country_target
FROM members m
WHERE COALESCE(m.last_active_at, m.join_time) < NOW() - INTERVAL '3 days'
  AND m.current_stage NOT IN ('Churned')

UNION ALL

SELECT
    'vendor_overdue' AS alert_type,
    vt.id::TEXT,
    vt.title,
    vt.status,
    EXTRACT(DAY FROM NOW() - vt.deadline)::INTEGER,
    vt.country_target
FROM vendor_tasks vt
WHERE vt.status IN ('assigned', 'ready_to_post')
  AND vt.deadline < NOW()

UNION ALL

SELECT
    'x_zero_joins' AS alert_type,
    xa.id,
    xa.handle,
    'posts but zero joins' AS detail,
    NULL::INTEGER,
    xa.country_target
FROM x_accounts xa
WHERE xa.status = 'active'
  AND NOT EXISTS (
      SELECT 1 FROM leads l WHERE l.source_account = xa.id
  )

UNION ALL

SELECT
    'country_crawl_no_data' AS alert_type,
    ci.id::TEXT,
    ci.country_target,
    COALESCE(ci.noise_warning, 'crawl with no useful data') AS detail,
    EXTRACT(DAY FROM NOW() - ci.created_at::TIMESTAMPTZ)::INTEGER,
    ci.country_target
FROM country_intelligence ci
WHERE ci.report_date >= CURRENT_DATE - INTERVAL '7 days'
  AND (ci.posts_crawled = 0 OR ci.high_potential_count = 0)

UNION ALL

SELECT
    'automation_failure' AS alert_type,
    al.id::TEXT,
    al.action,
    al.message,
    NULL::INTEGER,
    NULL
FROM activity_logs al
WHERE al.status = 'failure'
  AND al.created_at > NOW() - INTERVAL '24 hours'

ORDER BY alert_type, days_stuck DESC NULLS LAST;

-- ---------------------------------------------------------------------------
-- v_system_health — latest health check per service
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_system_health AS
SELECT DISTINCT ON (sh.service_name)
    sh.service_name,
    sh.status,
    sh.latency_ms,
    sh.message,
    sh.details,
    sh.checked_at
FROM system_health_logs sh
ORDER BY sh.service_name, sh.checked_at DESC;

-- ---------------------------------------------------------------------------
-- v_growth_overview — founder KPI snapshot (Section 1)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_growth_overview AS
SELECT
    CURRENT_DATE AS as_of_date,
    (SELECT COUNT(*) FROM telegram_joins WHERE DATE(join_time) = CURRENT_DATE) AS joins_today,
    (SELECT COUNT(*) FROM telegram_joins WHERE join_time >= CURRENT_DATE - INTERVAL '7 days') AS joins_7d,
    (SELECT COUNT(*) FROM telegram_joins WHERE join_time >= CURRENT_DATE - INTERVAL '30 days') AS joins_30d,
    (SELECT country_target FROM leads
     WHERE join_time >= CURRENT_DATE - INTERVAL '30 days' AND country_target IS NOT NULL
     GROUP BY country_target ORDER BY COUNT(*) DESC LIMIT 1) AS top_country_30d,
    (SELECT source_account FROM leads
     WHERE join_time >= CURRENT_DATE - INTERVAL '30 days' AND source_account IS NOT NULL
     GROUP BY source_account ORDER BY COUNT(*) DESC LIMIT 1) AS top_x_account_30d,
    (SELECT v.name FROM leads l
     JOIN vendors v ON v.id = l.vendor_id
     WHERE l.join_time >= CURRENT_DATE - INTERVAL '30 days'
     GROUP BY v.name ORDER BY COUNT(*) DESC LIMIT 1) AS top_vendor_30d,
    (SELECT ROUND(AVG(
        c.budget_usd / NULLIF(
            (SELECT COUNT(*) FROM leads l2 WHERE l2.campaign_id = c.id), 0
        )), 4)
     FROM campaigns c
     WHERE c.budget_usd IS NOT NULL AND c.budget_usd > 0) AS avg_cost_per_join;

-- ---------------------------------------------------------------------------
-- v_x_account_performance — joins by X account (Growth section)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_x_account_performance AS
SELECT
    xa.id AS x_account_id,
    xa.handle,
    xa.display_name,
    xa.country_target,
    xa.status,
    COUNT(DISTINCT l.id) AS total_leads,
    COUNT(DISTINCT l.id) FILTER (WHERE DATE(l.join_time) = CURRENT_DATE) AS joins_today,
    COUNT(DISTINCT l.id) FILTER (WHERE l.join_time >= CURRENT_DATE - INTERVAL '7 days') AS joins_7d,
    COUNT(DISTINCT cp.id) AS content_posts_tracked,
    COUNT(DISTINCT l.id) FILTER (WHERE l.current_stage = 'Paid / VIP') AS paid_vip_count,
    MAX(l.join_time) AS last_join_time
FROM x_accounts xa
LEFT JOIN leads l ON l.source_account = xa.id
LEFT JOIN content_performance cp ON cp.x_account_id = xa.id
GROUP BY xa.id, xa.handle, xa.display_name, xa.country_target, xa.status
ORDER BY total_leads DESC;

-- ---------------------------------------------------------------------------
-- v_campaign_performance — cost per join by campaign
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_campaign_performance AS
SELECT
    c.id AS campaign_id,
    c.name AS campaign_name,
    c.country_target,
    c.budget_usd,
    c.status,
    xa.handle AS x_account_handle,
    COUNT(DISTINCT l.id) AS telegram_joins,
    ROUND(c.budget_usd / NULLIF(COUNT(DISTINCT l.id), 0), 4) AS cost_per_join,
    MAX(l.join_time) AS last_join_time
FROM campaigns c
LEFT JOIN leads l ON l.campaign_id = c.id
LEFT JOIN x_accounts xa ON xa.id = c.x_account_id
GROUP BY c.id, c.name, c.country_target, c.budget_usd, c.status, xa.handle
ORDER BY telegram_joins DESC;

-- ---------------------------------------------------------------------------
-- v_content_leaderboard — top hook, hashtag, angle
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_content_leaderboard AS
SELECT
    'hook' AS metric_type,
    cp.hook AS metric_value,
    cp.country_target,
    SUM(cp.telegram_joins) AS total_joins,
    ROUND(AVG(cp.join_rate), 4) AS avg_join_rate,
    COUNT(*) AS post_count
FROM content_performance cp
WHERE cp.hook IS NOT NULL AND cp.hook <> ''
GROUP BY cp.hook, cp.country_target

UNION ALL

SELECT
    'hashtag',
    cp.hashtag,
    cp.country_target,
    SUM(cp.telegram_joins),
    ROUND(AVG(cp.join_rate), 4),
    COUNT(*)
FROM content_performance cp
WHERE cp.hashtag IS NOT NULL AND cp.hashtag <> ''
GROUP BY cp.hashtag, cp.country_target

UNION ALL

SELECT
    'angle',
    cp.angle,
    cp.country_target,
    SUM(cp.telegram_joins),
    ROUND(AVG(cp.join_rate), 4),
    COUNT(*)
FROM content_performance cp
WHERE cp.angle IS NOT NULL AND cp.angle <> ''
GROUP BY cp.angle, cp.country_target

ORDER BY metric_type, total_joins DESC;

-- ---------------------------------------------------------------------------
-- v_apify_crawl_health — Apify intelligence health (Section 7)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_apify_crawl_health AS
SELECT
    COALESCE(ap.crawl_run_id, 'unknown') AS crawl_run_id,
    MAX(ap.created_at) AS last_crawl_at,
    COUNT(*) AS posts_crawled,
    COUNT(*) FILTER (WHERE ap.lead_potential = 'High') AS high_potential_posts,
    COUNT(*) FILTER (WHERE ap.category = 'noise') AS noise_posts,
    COUNT(DISTINCT ap.country_target) AS countries_crawled,
    COUNT(DISTINCT ap.hashtag) AS hashtags_seen,
    ROUND(AVG(ap.engagement_score), 2) AS avg_engagement_score
FROM apify_posts ap
GROUP BY ap.crawl_run_id
ORDER BY last_crawl_at DESC NULLS LAST;

-- ---------------------------------------------------------------------------
-- v_country_intelligence_summary — daily intel rollup for dashboard
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_country_intelligence_summary AS
SELECT
    ci.report_date,
    ci.country_target,
    ci.top_hashtag,
    ci.top_hook,
    ci.top_author,
    ci.top_content_angle,
    ci.posts_crawled,
    ci.high_potential_count,
    ci.noise_warning,
    CASE
        WHEN ci.posts_crawled = 0 THEN 'no_data'
        WHEN ci.high_potential_count = 0 THEN 'low_value'
        ELSE 'ok'
    END AS crawl_quality
FROM country_intelligence ci
ORDER BY ci.report_date DESC, ci.high_potential_count DESC;

-- ---------------------------------------------------------------------------
-- v_crm_conversion — stage-to-stage conversion rates
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_crm_conversion AS
WITH stage_counts AS (
    SELECT cs.name AS stage_name, cs.sort_order, COUNT(l.id) AS lead_count
    FROM crm_stages cs
    LEFT JOIN leads l ON l.current_stage = cs.name
    GROUP BY cs.name, cs.sort_order
),
total AS (
    SELECT NULLIF(SUM(lead_count), 0) AS total_leads FROM stage_counts
)
SELECT
    sc.stage_name,
    sc.sort_order,
    sc.lead_count,
    ROUND(100.0 * sc.lead_count / t.total_leads, 2) AS pct_of_pipeline,
    LAG(sc.lead_count) OVER (ORDER BY sc.sort_order) AS prev_stage_count,
    ROUND(100.0 * sc.lead_count / NULLIF(LAG(sc.lead_count) OVER (ORDER BY sc.sort_order), 0), 2) AS conversion_from_prev_pct
FROM stage_counts sc
CROSS JOIN total t
ORDER BY sc.sort_order;

-- ---------------------------------------------------------------------------
-- v_daily_kpis_dashboard — founder daily rollup (links to daily_kpis table)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_kpis_dashboard AS
SELECT
    dk.kpi_date,
    dk.telegram_joins,
    dk.top_country,
    dk.top_x_account,
    dk.top_vendor,
    dk.cost_per_join,
    dk.new_x_visitor,
    dk.telegram_joined,
    dk.warm_member,
    dk.signal_interested,
    dk.paid_vip,
    dk.renewal_risk,
    dk.posts_tracked,
    dk.winning_hook,
    dk.top_hashtag,
    dk.best_content_angle,
    dk.apify_run_status,
    dk.apify_posts_crawled,
    dk.apify_high_potential,
    dk.vendor_tasks_created,
    dk.vendor_tasks_posted,
    dk.vendor_tasks_overdue
FROM daily_kpis dk
ORDER BY dk.kpi_date DESC;

