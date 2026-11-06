CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS policies (
    policy_number VARCHAR(50) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL,
    product VARCHAR(100) NOT NULL,
    coverage_limit NUMERIC(14,2) NOT NULL,
    deductible NUMERIC(14,2) DEFAULT 0,
    active BOOLEAN DEFAULT TRUE,
    wording TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cases (
    case_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_number VARCHAR(50) UNIQUE NOT NULL,
    policy_number VARCHAR(50) REFERENCES policies(policy_number),
    claimant_name VARCHAR(200) NOT NULL,
    claimant_email VARCHAR(320),
    claim_type VARCHAR(100) NOT NULL,
    claim_amount NUMERIC(14,2) NOT NULL,
    incident_date DATE,
    description TEXT,
    status VARCHAR(50) DEFAULT 'submitted',
    next_step VARCHAR(100) DEFAULT 'intake',
    assigned_adjuster VARCHAR(200),
    assigned_approver VARCHAR(200),
    duplicate_case_id UUID,
    summary JSONB,
    risks JSONB DEFAULT '[]'::jsonb,
    missing_documents JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    document_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(case_id) ON DELETE CASCADE,
    file_name VARCHAR(500) NOT NULL,
    file_path TEXT NOT NULL,
    document_type VARCHAR(100),
    extracted_text TEXT,
    extracted_fields JSONB DEFAULT '{}'::jsonb,
    ocr_confidence NUMERIC(5,4),
    injection_detected BOOLEAN DEFAULT FALSE,
    validation_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staff (
    staff_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(320) UNIQUE NOT NULL,
    role VARCHAR(50) NOT NULL,
    approval_limit NUMERIC(14,2) DEFAULT 0,
    active_cases INTEGER DEFAULT 0,
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(case_id) ON DELETE CASCADE,
    approver_email VARCHAR(320),
    requested_at TIMESTAMPTZ DEFAULT NOW(),
    decision VARCHAR(50),
    rationale TEXT,
    decided_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    case_id UUID,
    actor VARCHAR(200) NOT NULL,
    action VARCHAR(200) NOT NULL,
    before_state JSONB,
    after_state JSONB,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sla_events (
    sla_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES cases(case_id) ON DELETE CASCADE,
    sla_type VARCHAR(100) NOT NULL,
    due_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    escalated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO policies (
    policy_number,
    customer_name,
    product,
    coverage_limit,
    deductible,
    wording
)
VALUES (
    'POL-10001',
    'John Test Customer',
    'Health Claims',
    100000.00,
    500.00,
    'Covered claims require a completed claim form, invoice and medical report. Claims above 50000 require senior approval. Experimental treatment is excluded unless pre-authorised.'
)
ON CONFLICT (policy_number) DO NOTHING;

INSERT INTO staff (full_name, email, role, approval_limit, active_cases)
VALUES
    ('Anita Adjuster', 'adjuster@lab.local', 'adjuster', 0, 2),
    ('Ravi Approver', 'approver@lab.local', 'approver', 50000, 1),
    ('Meera Senior Approver', 'senior.approver@lab.local', 'approver', 250000, 3),
    ('Suresh Supervisor', 'supervisor@lab.local', 'supervisor', 500000, 1)
ON CONFLICT (email) DO NOTHING;
