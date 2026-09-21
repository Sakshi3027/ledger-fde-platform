CREATE TABLE claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    claim_id TEXT NOT NULL,
    desynpuf_id TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    provider_specialty TEXT,
    procedure_code TEXT NOT NULL,
    diagnosis_code TEXT NOT NULL,
    claim_type TEXT,
    billed_amount NUMERIC(10, 2) NOT NULL,
    submitted_date DATE NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, adjudicated, flagged
    UNIQUE (client_id, claim_id)
);

CREATE TABLE quarantined_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id),
    raw_data JSONB NOT NULL,          -- the original row, whatever shape it came in
    reason TEXT NOT NULL,             -- why it failed the quality gate
    quarantined_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claims_client_id ON claims(client_id);
CREATE INDEX idx_claims_status ON claims(status);
CREATE INDEX idx_quarantined_client_id ON quarantined_records(client_id);
