import os
import re
import json
import sys
from collections import defaultdict
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

def main():
    print("=" * 80)
    print("BNSS -> CrPC SECTION MAPPING & INGESTION")
    print("=" * 80)

    # 1. Load Environment & Neo4j Connection
    dotenv_path = Path(__file__).parent.parent / ".env"
    if not dotenv_path.exists():
        dotenv_path = Path(".env")
    load_dotenv(dotenv_path)

    uri = os.getenv('NEO4J_URI')
    user = os.getenv('NEO4J_USER') or os.getenv('NEO4J_USERNAME')
    pwd = os.getenv('NEO4J_PASSWORD')
    db = os.getenv('NEO4J_DATABASE', 'neo4j')

    if not all([uri, user, pwd]):
        print(f"[ERROR] Missing Neo4j credentials in {dotenv_path}")
        sys.exit(1)

    print(f"Connecting to Neo4j at {uri} (database: {db})...")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    # 2. Query Neo4j for BNSS -[:REPLACES]-> CrPC relationships
    print("Querying Neo4j for (BNSS)-[:REPLACES]->(CrPC) edges...")
    query = """
        MATCH (a)-[r:REPLACES]->(b)
        WHERE (a.act = 'BNSS' OR 'BNSSSection' IN labels(a))
          AND (b.act = 'CrPC' OR 'CrPCSection' IN labels(b))

        RETURN a.id AS a_id, a.section AS a_sec, a.title AS a_title,
               b.id AS b_id, b.section AS b_sec, b.title AS b_title
        ORDER BY a.section
    """
    with driver.session(database=db) as session:
        res = session.run(query)
        records = [dict(r) for r in res]
    driver.close()
    print(f"Retrieved {len(records)} REPLACES relationships from Neo4j.\n")

    # Map BNSS section -> list of CrPC sections
    bnss_to_crpc_map = defaultdict(list)
    for r in records:
        a_sec = str(r['a_sec']).strip() if r['a_sec'] is not None else str(r['a_id']).replace('BNSS_', '').strip()
        b_sec = str(r['b_sec']).strip() if r['b_sec'] is not None else str(r['b_id']).replace('CrPC_', '').strip()
        if a_sec and b_sec:
            if b_sec not in bnss_to_crpc_map[a_sec]:
                bnss_to_crpc_map[a_sec].append(b_sec)
            m = re.match(r'^(\d+)', a_sec)
            if m:
                base = m.group(1)
                if b_sec not in bnss_to_crpc_map[base]:
                    bnss_to_crpc_map[base].append(b_sec)


    def sort_key(s):
        m = re.match(r'^(\d+)([A-Za-z]*)', s)
        if m:
            return (int(m.group(1)), m.group(2))
        return (9999, s)

    def get_crpc_mapping(sec_num_str):
        clean_num = str(sec_num_str).strip()
        rels = bnss_to_crpc_map.get(clean_num, [])
        if not rels:
            # Check base numeric match
            m = re.match(r'^(\d+)', clean_num)
            if m:
                rels = bnss_to_crpc_map.get(m.group(1), [])
        if not rels:
            return None
        rels.sort(key=sort_key)
        return ", ".join(rels)

    # 3. Update bnss_bail_core.json
    core_path = Path(__file__).parent / "bnss_bail_core.json"
    print(f"Updating {core_path}...")
    with open(core_path, 'r', encoding='utf-8') as f:
        core_data = json.load(f)

    core_mapped = 0
    total_core = len(core_data.get('sections', []))
    for sec in core_data.get('sections', []):
        sec_num = str(sec.get('section_number', '')).strip()
        crpc_equiv = get_crpc_mapping(sec_num)
        sec['replaces_CrPC'] = crpc_equiv
        if crpc_equiv:
            core_mapped += 1

    with open(core_path, 'w', encoding='utf-8') as f:
        json.dump(core_data, f, indent=2, ensure_ascii=False)
    print(f"Updated bnss_bail_core.json: {core_mapped}/{total_core} sections mapped to CrPC.")

    # 4. Update bnss.json (fallback full corpus)
    fallback_path = Path(__file__).parent / "bnss.json"
    print(f"\nUpdating {fallback_path}...")
    with open(fallback_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)

    full_mapped = 0
    total_full = 0
    print("-" * 80)
    print(f"{'SEC':>4} | {'BNSS HEADING':<45} | {'REPLACES CrPC':<20} | STATUS")
    print("-" * 80)

    for chapter in full_data.get('chapters', []):
        for sec in chapter.get('sections', []):
            total_full += 1
            sec_num = str(sec.get('section_number', '')).strip()
            heading = sec.get('heading', '') or ''
            truncated_heading = (heading[:42] + '...') if len(heading) > 45 else heading

            crpc_equiv = get_crpc_mapping(sec_num)
            sec['replaces_CrPC'] = crpc_equiv

            if crpc_equiv:
                full_mapped += 1
                status = "MAPPED"
                if total_full <= 25 or sec_num in ['35', '187', '479', '480', '482']:
                    print(f"{sec_num:>4} | {truncated_heading:<45} | {crpc_equiv:<20} | {status}")
            else:
                if total_full <= 15:
                    print(f"{sec_num:>4} | {truncated_heading:<45} | {'None':<20} | NOT FOUND")

    with open(fallback_path, 'w', encoding='utf-8') as f:
        json.dump(full_data, f, indent=2, ensure_ascii=False)
    print(f"\nUpdated bnss.json: {full_mapped}/{total_full} sections mapped to CrPC.")

    # 5. Summary
    print("=" * 80)
    print("SUMMARY")
    print(f"Total BNSS sections in Neo4j          : {len(records)}")
    print(f"bnss_bail_core.json mapped to CrPC    : {core_mapped}/{total_core}")
    print(f"bnss.json (full corpus) mapped to CrPC: {full_mapped}/{total_full}")
    print("Key Bail Sections verified:")
    for k in ['35', '187', '479', '480', '482']:
        print(f"  BNSS {k:>3} --> CrPC {get_crpc_mapping(k)}")
    print("=" * 80)


if __name__ == '__main__':
    main()
