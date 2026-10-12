import os
import re
import json
import sys
from collections import defaultdict
from dotenv import load_dotenv
from neo4j import GraphDatabase

def main():
    print("=" * 80)
    print("BSA -> IEA SECTION MAPPING & INGESTION")
    print("=" * 80)

    # 1. Load Environment & Neo4j Connection
    dotenv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '.env'))
    load_dotenv(dotenv_path)

    uri = os.getenv('NEO4J_URI')
    user = os.getenv('NEO4J_USER')
    pwd = os.getenv('NEO4J_PASSWORD')
    db = os.getenv('NEO4J_DATABASE', 'neo4j')

    if not all([uri, user, pwd]):
        print(f"[ERROR] Missing Neo4j credentials in {dotenv_path}")
        sys.exit(1)

    print(f"Connecting to Neo4j at {uri} (database: {db})...")
    driver = GraphDatabase.driver(uri, auth=(user, pwd))

    # 2. Query Neo4j for BSA -[:REPLACES]-> IEA relationships
    print("Querying Neo4j for (BSA)-[:REPLACES]->(IEA) edges...")
    query = """
        MATCH (a)-[r:REPLACES]->(b)
        WHERE (a.act = 'BSA' OR 'BSASection' IN labels(a))
          AND (b.act = 'IEA' OR 'IEASection' IN labels(b))
        RETURN a.id AS a_id, a.section AS a_sec, a.title AS a_title,
               b.id AS b_id, b.section AS b_sec, b.title AS b_title
        ORDER BY a.id
    """
    with driver.session(database=db) as session:
        res = session.run(query)
        records = [dict(r) for r in res]
    driver.close()
    print(f"Retrieved {len(records)} REPLACES relationships from Neo4j.\n")

    # Group relationships by base section number
    base_map = defaultdict(list)
    for r in records:
        a_sec = str(r['a_sec']).strip() if r['a_sec'] is not None else str(r['a_id']).replace('BSA_', '').strip()
        m = re.match(r'^(\d+)', a_sec)
        if m:
            base_num = m.group(1)
            base_map[base_num].append(r)
        else:
            base_map[a_sec].append(r)

    def sort_key(s):
        m = re.match(r'^(\d+)([A-Za-z]*)', s)
        if m:
            return (int(m.group(1)), m.group(2))
        return (9999, s)

    # Pre-build section mapping
    def get_iea_mapping(sec_num_str):
        rels = base_map.get(sec_num_str, [])
        if not rels:
            return None
        iea_secs = []
        for r in rels:
            b_sec = str(r['b_sec']).strip() if r['b_sec'] is not None else str(r['b_id']).replace('IEA_', '').strip()
            if b_sec and b_sec not in iea_secs:
                iea_secs.append(b_sec)
        iea_secs.sort(key=sort_key)
        return ", ".join(iea_secs) if iea_secs else None

    # 3. Load bsa.json
    bsa_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'bsa.json'))
    print(f"Loading {bsa_file_path}...")
    with open(bsa_file_path, 'r', encoding='utf-8') as f:
        bsa_data = json.load(f)

    # 4. Process each section and add replaces_IEA
    print("-" * 80)
    print(f"{'SEC':>4} | {'BSA HEADING':<45} | {'REPLACES IEA':<20} | STATUS")
    print("-" * 80)

    total_sections = 0
    mapped_count = 0
    unmapped_sections = []
    multi_mapped_sections = []

    for chapter in bsa_data.get('chapters', []):
        new_sections = []
        for sec in chapter.get('sections', []):
            total_sections += 1
            sec_num = str(sec.get('section_number', '')).strip()
            heading = sec.get('heading', '') or ''
            truncated_heading = (heading[:42] + '...') if len(heading) > 45 else heading

            iea_equiv = get_iea_mapping(sec_num)

            # Reconstruct dictionary with replaces_IEA right after section_number
            updated_sec = {}
            for k, v in sec.items():
                updated_sec[k] = v
                if k == 'section_number':
                    updated_sec['replaces_IEA'] = iea_equiv

            # If section_number wasn't in keys for some reason, ensure field is present
            if 'replaces_IEA' not in updated_sec:
                updated_sec['replaces_IEA'] = iea_equiv

            new_sections.append(updated_sec)

            if iea_equiv is not None:
                mapped_count += 1
                if ',' in iea_equiv:
                    multi_mapped_sections.append((sec_num, heading, iea_equiv))
                    status = "MAPPED (MULTI)"
                else:
                    status = "MAPPED"
                print(f"{sec_num:>4} | {truncated_heading:<45} | {iea_equiv:<20} | {status}")
            else:
                unmapped_sections.append((sec_num, heading))
                print(f"{sec_num:>4} | {truncated_heading:<45} | {'None':<20} | NOT FOUND")

        chapter['sections'] = new_sections

    # 5. Save updated bsa.json
    print("-" * 80)
    print(f"Writing updated data back to {bsa_file_path}...")
    with open(bsa_file_path, 'w', encoding='utf-8') as f:
        json.dump(bsa_data, f, indent=2, ensure_ascii=False)
    print("File saved successfully.")

    # 6. Final Summary Report
    print("=" * 80)
    print("SUMMARY REPORT")
    print("=" * 80)
    print(f"Total BSA sections processed : {total_sections}")
    print(f"Successfully mapped to IEA   : {mapped_count}")
    print(f"Unmapped sections (not found): {len(unmapped_sections)}")

    if multi_mapped_sections:
        print(f"\nSections mapped to multiple IEA sections ({len(multi_mapped_sections)}):")
        for s_num, h, iea in multi_mapped_sections:
            print(f"  - BSA Section {s_num:>3} ('{h}'): IEA {iea}")

    if unmapped_sections:
        print(f"\nSections not found in Neo4j IEA mappings ({len(unmapped_sections)}):")
        for s_num, h in unmapped_sections:
            print(f"  - BSA Section {s_num:>3}: '{h}'")
    print("=" * 80)

if __name__ == '__main__':
    main()
