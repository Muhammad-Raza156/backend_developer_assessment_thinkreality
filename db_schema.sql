-- Table: units
-- This schema is compatible with the insert statements.
CREATE TABLE units (
    unit_id UUID PRIMARY KEY,
    unique_key VARCHAR UNIQUE NOT NULL,
    building_name VARCHAR NOT NULL,
    unit_number VARCHAR NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Table: owners
-- This schema is derived from the columns in the INSERT statement.
CREATE TABLE owners (
    owner_id UUID PRIMARY KEY,
    owner_type VARCHAR NOT NULL,
    full_name VARCHAR,
    first_name VARCHAR,
    last_name VARCHAR,
    date_of_birth DATE,
    nationality VARCHAR,
    company_name VARCHAR,
    company_type VARCHAR,
    trade_license_number VARCHAR,
    phone_primary VARCHAR,
    phone_secondary VARCHAR,
    email VARCHAR,
    emirates_id VARCHAR UNIQUE,
    passport_number VARCHAR,
    visa_number VARCHAR,
    address_line1 VARCHAR,
    city VARCHAR,
    country VARCHAR,
    preferred_contact_method VARCHAR,
    communication_language VARCHAR,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT check_owner_type CHECK (owner_type IN ('individual', 'corporate')),
    CONSTRAINT check_individual_owner_eid CHECK (NOT (owner_type = 'individual' AND emirates_id IS NULL)),
    CONSTRAINT check_emirates_id_format CHECK (emirates_id IS NULL OR emirates_id ~ '^784-[0-9]{4}-[0-9]{7}-[0-9]{1}$')
);

-- Table: ownership_history
-- This schema is derived from the columns in the INSERT statement.
CREATE TABLE ownership_history (
    history_id INT PRIMARY KEY,
    unit_id UUID NOT NULL,
    owner_id UUID NOT NULL,
    ownership_start_date DATE NOT NULL,
    ownership_end_date DATE,
    ownership_percentage FLOAT NOT NULL,
    is_current_owner BOOLEAN NOT NULL,
    purchase_price FLOAT,
    purchase_currency VARCHAR(3),
    financing_type VARCHAR,
    title_deed_number VARCHAR,
    registration_number VARCHAR,
    transaction_type VARCHAR,
    transfer_reason VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT fk_ownership_history_unit FOREIGN KEY(unit_id) REFERENCES units(unit_id),
    CONSTRAINT fk_ownership_history_owner FOREIGN KEY(owner_id) REFERENCES owners(owner_id),
    CONSTRAINT ownership_percentage_check CHECK (ownership_percentage > 0 AND ownership_percentage <= 100)
);

-- Table: ownership_transfers
-- This schema is derived from the columns in the INSERT statement.
CREATE TABLE ownership_transfers (
    transfer_id INT PRIMARY KEY,
    unit_id UUID NOT NULL,
    transfer_type VARCHAR NOT NULL,
    transfer_date DATE NOT NULL,
    total_amount FLOAT,
    transfer_currency VARCHAR(3),
    legal_reason VARCHAR,
    status VARCHAR,
    initiated_by VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT fk_ownership_transfers_unit FOREIGN KEY(unit_id) REFERENCES units(unit_id),
    CONSTRAINT transfer_date_not_in_future_check CHECK (transfer_date <= now())
);

-- Table: transfer_documents
-- This schema is derived from the columns in the INSERT statement.
CREATE TABLE transfer_documents (
    document_id INT PRIMARY KEY,
    transfer_id INT NOT NULL,
    document_type VARCHAR,
    document_name VARCHAR,
    file_path VARCHAR,
    upload_date DATE,
    uploaded_by VARCHAR,
    verification_status VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT fk_transfer_documents_transfer FOREIGN KEY(transfer_id) REFERENCES ownership_transfers(transfer_id)
);

-- Table: audit_logs
-- This schema is derived from the columns in the INSERT statement.
CREATE TABLE audit_logs (
    log_id INT PRIMARY KEY,
    table_name VARCHAR,
    record_id VARCHAR,
    action VARCHAR,
    old_values JSONB,
    new_values JSONB,
    changed_by VARCHAR,
    change_reason VARCHAR,
    ip_address VARCHAR,
    user_agent VARCHAR,
    created_at TIMESTAMP NOT NULL DEFAULT now()
);

-- Indexes for performance
CREATE INDEX idx_ownership_history_unit_id ON ownership_history(unit_id);
CREATE INDEX idx_ownership_history_owner_id ON ownership_history(owner_id);

CREATE INDEX idx_ownership_transfers_unit_id ON ownership_transfers(unit_id);

CREATE INDEX idx_transfer_documents_transfer_id ON transfer_documents(transfer_id);

CREATE INDEX idx_audit_logs_record_id ON audit_logs(record_id);
CREATE INDEX idx_audit_logs_changed_by ON audit_logs(changed_by);

