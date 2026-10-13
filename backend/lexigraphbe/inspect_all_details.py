import os
import json
from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv('backend/.env')

uri = os.getenv('NEO4J_URI')
user = os.getenv('NEO4J_USER')
pwd = os.getenv('NEO4J_PASSWORD')
db = os.getenv('NEO4J_DATABASE', 'neo4j')

driver = GraphDatabase.driver(uri, auth=(user, pwd))
with driver.session(database=db) as session:
    res = session.run('''
        MATCH (a)-[r:REPLACES]->(b)
        WHERE a.act = 'BSA'
        RETURN a.id AS a_id, a.section AS a_sec, a.title AS a_title,
               b.id AS b_id, b.section AS b_sec, b.title AS b_title
        ORDER BY a.id
    ''')
    records = [dict(r) for r in res]
driver.close()

with open('backend/lexigraphbe/bsa.json', 'r', encoding='utf-8') as f:
    bsa = json.load(f)

bsa_sections = {}
for ch in bsa['chapters']:
    for s in ch['sections']:
        bsa_sections[str(s['section_number']).strip()] = s

print("--- DETAILED MAPPING INSPECTION ---")
print(f"Total sections in bsa.json: {len(bsa_sections)}")
print(f"Total REPLACES in Neo4j: {len(records)}")

# Group mappings by base section number
from collections import defaultdict
import re

base_map = defaultdict(list)
for r in records:
    a_sec = r['a_sec']
    # extract base number
    match = re.match(r'^(\d+)', str(a_sec))
    if match:
        base_sec = match.group(1)
        base_map[base_sec].append(r)
    else:
        print(f"Non-numeric section: {a_sec}")

print("\n--- Summary per base section ---")
for base_num in sorted(bsa_sections.keys(), key=lambda x: int(x) if x.isdigit() else 999):
    mappings = base_map.get(base_num, [])
    if not mappings:
        print(f"BSA {base_num} ({bsa_sections[base_num]['heading']}): NO IEA MAPPING FOUND IN NEO4J")
    elif len(mappings) == 1:
        m = mappings[0]
        if m['a_sec'] == base_num:
            pass # 1-to-1 exact match
        else:
            print(f"BSA {base_num}: mapped via {m['a_sec']} -> IEA {m['b_sec']}")
    else:
        print(f"BSA {base_num} ({bsa_sections[base_num]['heading']}): MULTIPLE IEA MAPPINGS:")
        for m in mappings:
            print(f"   {m['a_sec']} -> IEA {m['b_sec']} ({m['b_title']})")
