"""
Fix the search_propositions PostgreSQL function.
The relevance_score expression produces 'numeric' but the return type is FLOAT (double precision).
Adding ::FLOAT cast resolves the type mismatch.
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

connection_string = os.getenv(
    "POSTGRES_URL",
    "postgresql://localhost:5432/bail_precedents"
)

FUNC_SQL = """
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
            p.normalized_statutes && search_statutes
            OR
            p.tags && search_tags
        )
        AND (search_stage IS NULL OR c.procedural_stage = search_stage)
        AND (favors_filter IS NULL OR p.favors = favors_filter)
        AND (min_year IS NULL OR EXTRACT(YEAR FROM c.decided_on) >= min_year)
    ORDER BY relevance_score DESC, c.decided_on DESC
    LIMIT limit_results;
END;
$$ LANGUAGE plpgsql;
"""

def main():
    print(f"Connecting to: {connection_string[:40]}...")
    conn = psycopg2.connect(connection_string)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(FUNC_SQL)
        print("✓ search_propositions function updated successfully!")
        # Quick smoke-test
        cur.execute("SELECT search_propositions(ARRAY['IPC-1860:420']::TEXT[], ARRAY['bail_not_jail']::TEXT[], NULL, NULL, NULL, 5);")
        rows = cur.fetchall()
        print(f"✓ Smoke test passed — {len(rows)} result(s) returned.")
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    main()
