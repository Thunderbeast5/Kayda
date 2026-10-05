import os
import json
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv('backend/.env')

uri = os.getenv('NEO4J_URI')
user = os.getenv('NEO4J_USER')
pwd = os.getenv('NEO4J_PASSWORD')
db = os.getenv('NEO4J_DATABASE', 'neo4j')

# Load bsa.json
with open('backend/lexigraphbe/bsa.json', 'r', encoding='utf-8') as f:
    bsa_data = json.load(f)

json_sections = []
for ch in bsa_data.get('chapters', []):
    for sec in ch.get('sections', []):
        json_sections.append(str(sec.get('section_number')).strip())

print(f"Total sections in bsa.json: {len(json_sections)}")
print(f"Sample sections in bsa.json: {json_sections[:15]}")

driver = GraphDatabase.driver(uri, auth=(user, pwd))
with driver.session(database=db) as session:
    res = session.run('''
        MATCH (a)-[r:REPLACES]->(b)
        WHERE a.act = 'BSA'
        RETURN a.id AS a_id, a.section AS a_sec, b.id AS b_id, b.section AS b_sec
    ''')
    neo_map = {}
    for r in res:
        bsa_sec = str(r['a_sec']).strip() if r['a_sec'] is not None else str(r['a_id']).replace('BSA_', '').strip()
        iea_sec = str(r['b_sec']).strip() if r['b_sec'] is not None else str(r['b_id']).replace('IEA_', '').strip()
        neo_map[bsa_sec] = iea_sec

driver.close()

print(f"Total mappings found in Neo4j: {len(neo_map)}")

# Check matching
matched = []
unmatched = []
for sec_num in json_sections:
    if sec_num in neo_map:
        matched.append((sec_num, neo_map[sec_num]))
    else:
        unmatched.append(sec_num)

print(f"\nMatched count: {len(matched)}")
print(f"Unmatched count: {len(unmatched)}")
if unmatched:
    print(f"Unmatched section numbers: {unmatched}")

# Check any keys in neo_map not in json_sections
extra_in_neo = set(neo_map.keys()) - set(json_sections)
print(f"Keys in Neo4j not in bsa.json: {extra_in_neo}")
