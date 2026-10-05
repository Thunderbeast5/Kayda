-- PostgreSQL Schema for Bail Precedent Database
-- Stores normalized case data with structured retrieval support

-- Ensure we're using the public schema (no special permissions needed if database owner)
SET search_path TO public;

-- Cases table
CREATE TABLE IF NOT EXISTS bail_cases (
    case_id VARCHAR(255) PRIMARY KEY,
    case_name TEXT NOT NULL,
    petitioner TEXT,
    respondent TEXT,
    court VARCHAR(100),
    decided_on DATE,
    bench_strength INTEGER,
    procedural_stage VARCHAR(50),
    offence_types TEXT[],
    dispute_nature VARCHAR(100),
    abstract_facts TEXT,
    disposition TEXT,
    lower_court_outcome TEXT,
    normalized_statutes TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes on cases table
CREATE INDEX IF NOT EXISTS idx_cases_court ON bail_cases(court);
CREATE INDEX IF NOT EXISTS idx_cases_stage ON bail_cases(procedural_stage);
CREATE INDEX IF NOT EXISTS idx_cases_decided_on ON bail_cases(decided_on);
CREATE INDEX IF NOT EXISTS idx_cases_statutes ON bail_cases USING GIN(normalized_statutes);

-- Propositions table
CREATE TABLE IF NOT EXISTS bail_propositions (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(255) NOT NULL REFERENCES bail_cases(case_id) ON DELETE CASCADE,
    proposition_id VARCHAR(50) NOT NULL,
    text TEXT NOT NULL,
    speaker VARCHAR(100),
    kind VARCHAR(50),
    is_holding BOOLEAN DEFAULT FALSE,
    favors VARCHAR(50),
    conditions TEXT[],
    normalized_statutes TEXT[],
    tags TEXT[],
    binding_level VARCHAR(50),
    authorities JSONB,
    anchors TEXT[],
    quote TEXT,
    quote_verified BOOLEAN DEFAULT FALSE,
    favors_verified BOOLEAN DEFAULT TRUE,
    verification_note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(case_id, proposition_id)
);

-- Create indexes on propositions table
CREATE INDEX IF NOT EXISTS idx_props_case_id ON bail_propositions(case_id);
CREATE INDEX IF NOT EXISTS idx_props_kind ON bail_propositions(kind);
CREATE INDEX IF NOT EXISTS idx_props_favors ON bail_propositions(favors);
CREATE INDEX IF NOT EXISTS idx_props_is_holding ON bail_propositions(is_holding);
CREATE INDEX IF NOT EXISTS idx_props_binding_level ON bail_propositions(binding_level);
CREATE INDEX IF NOT EXISTS idx_props_statutes ON bail_propositions USING GIN(normalized_statutes);
CREATE INDEX IF NOT EXISTS idx_props_tags ON bail_propositions USING GIN(tags);
CREATE INDEX IF NOT EXISTS idx_props_quote_verified ON bail_propositions(quote_verified);
CREATE INDEX IF NOT EXISTS idx_props_text_fts ON bail_propositions USING GIN(to_tsvector('english', text));

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS idx_props_retrieval ON bail_propositions(is_holding, quote_verified, binding_level, favors);

-- View for verified holdings only
CREATE OR REPLACE VIEW verified_holdings AS
SELECT 
    p.*,
    c.case_name,
    c.court,
    c.decided_on,
    c.procedural_stage
FROM bail_propositions p
JOIN bail_cases c ON p.case_id = c.case_id
WHERE p.is_holding = TRUE 
  AND p.quote_verified = TRUE
  AND p.favors_verified = TRUE;

-- View for high-quality propositions (for retrieval)
CREATE OR REPLACE VIEW high_quality_propositions AS
SELECT 
    p.*,
    c.case_name,
    c.court,
    c.decided_on,
    c.procedural_stage,
    c.bench_strength
FROM bail_propositions p
JOIN bail_cases c ON p.case_id = c.case_id
WHERE p.quote_verified = TRUE;

-- Function to search propositions by statute and tags
CREATE OR REPLACE FUNCTION search_propositions(
    search_statutes TEXT[],
    search_tags TEXT[],
    search_stage VARCHAR DEFAULT NULL,
    favors_filter VARCHAR DEFAULT NULL,
    min_year INTEGER DEFAULT NULL,
    limit_results INTEGER DEFAULT 50
)
RETURNS TABLE (
    proposition_id VARCHAR,
    case_id VARCHAR,
    case_name TEXT,
    court VARCHAR,
    decided_on DATE,
    text TEXT,
    quote TEXT,
    favors VARCHAR,
    tags TEXT[],
    normalized_statutes TEXT[],
    binding_level VARCHAR,
    relevance_score FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        p.proposition_id,
        p.case_id,
        c.case_name,
        c.court,
        c.decided_on,
        p.text,
        p.quote,
        p.favors,
        p.tags,
        p.normalized_statutes,
        p.binding_level,
        -- Scoring: statute overlap + tag overlap + binding bonus + holding bonus
        (
            COALESCE(array_length(ARRAY(SELECT unnest(p.normalized_statutes) INTERSECT SELECT unnest(search_statutes)), 1), 0) * 10.0 +
            COALESCE(array_length(ARRAY(SELECT unnest(p.tags) INTERSECT SELECT unnest(search_tags)), 1), 0) * 5.0 +
            CASE WHEN p.binding_level = 'binding' THEN 3.0 ELSE 0.0 END +
            CASE WHEN p.is_holding THEN 2.0 ELSE 0.0 END +
            CASE WHEN c.court = 'Supreme Court of India' THEN 2.0 ELSE 0.0 END
        )::FLOAT AS relevance_score
    FROM bail_propositions p
    JOIN bail_cases c ON p.case_id = c.case_id
    WHERE 
        p.quote_verified = TRUE
        AND (
            -- Statute overlap
            p.normalized_statutes && search_statutes
            OR
            -- Tag overlap
            p.tags && search_tags
        )
        AND (search_stage IS NULL OR c.procedural_stage = search_stage)
        AND (favors_filter IS NULL OR p.favors = favors_filter)
        AND (min_year IS NULL OR EXTRACT(YEAR FROM c.decided_on) >= min_year)
    ORDER BY relevance_score DESC, c.decided_on DESC
    LIMIT limit_results;
END;
$$ LANGUAGE plpgsql;

-- Statistics view
CREATE OR REPLACE VIEW database_stats AS
SELECT 
    (SELECT COUNT(*) FROM bail_cases) AS total_cases,
    (SELECT COUNT(*) FROM bail_propositions) AS total_propositions,
    (SELECT COUNT(*) FROM bail_propositions WHERE is_holding = TRUE) AS holdings,
    (SELECT COUNT(*) FROM bail_propositions WHERE quote_verified = TRUE) AS verified_propositions,
    (SELECT COUNT(*) FROM bail_propositions WHERE binding_level = 'binding') AS binding_propositions,
    (SELECT COUNT(DISTINCT tag) FROM bail_propositions, LATERAL unnest(tags) AS tag) AS unique_tags,
    (SELECT COUNT(DISTINCT statute) FROM bail_propositions, LATERAL unnest(normalized_statutes) AS statute) AS unique_statutes;

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_bail_cases_updated_at
BEFORE UPDATE ON bail_cases
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();
