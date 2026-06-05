-- 002_compliance_engine.sql
-- SitRep-FCE compliance engine foundation

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS compliance_audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    tenant_id TEXT DEFAULT 'default',

    observation_id UUID REFERENCES observations(id) ON DELETE SET NULL,
    entity_id UUID REFERENCES entities(id) ON DELETE SET NULL,
    fusion_output_id UUID REFERENCES fusion_outputs(id) ON DELETE SET NULL,

    policy_id TEXT NOT NULL,
    policy_version TEXT DEFAULT '0.1.0',
    rule_id TEXT NOT NULL,

    source_system TEXT,
    source_type TEXT,

    classification_in TEXT DEFAULT 'UNCLASSIFIED',
    classification_out TEXT DEFAULT 'UNCLASSIFIED',

    security_domain_in TEXT DEFAULT 'open_network',
    requested_output_domain TEXT DEFAULT 'operator_console',

    enforcement_action TEXT NOT NULL,
    compliance_disposition TEXT NOT NULL,

    reason TEXT,
    human_readable_decision TEXT,

    machine_readable_policy JSONB DEFAULT '{}'::jsonb,
    evidence JSONB DEFAULT '{}'::jsonb,

    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_tenant
ON compliance_audit_logs(tenant_id);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_observation
ON compliance_audit_logs(observation_id);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_fusion
ON compliance_audit_logs(fusion_output_id);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_created
ON compliance_audit_logs(created_at);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_action
ON compliance_audit_logs(enforcement_action);

CREATE INDEX IF NOT EXISTS idx_compliance_audit_disposition
ON compliance_audit_logs(compliance_disposition);
