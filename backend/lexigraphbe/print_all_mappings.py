import os
import re
import json
from collections import defaultdict
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
        WHERE a.act = 'BSA' AND b.act = 'IEA'
        RETURN a.id AS a_id, a.section AS a_sec, a.title AS a_title,
               b.id AS b_id, b.section AS b_sec, b.title AS b_title
        ORDER BY a.id
    ''')
    records = [dict(r) for r in res]
driver.close()

# Group by base section
base_map = defaultdict(list)
for r in records:
    a_sec = str(r['a_sec']).strip()
    m = re.match(r'^(\d+)', a_sec)
    if m:
        base_num = m.group(1)
        base_map[base_num].append(r)

def sort_key(s):
    # Sort helper for IEA section like '45', '45A'
    m = re.match(r'^(\d+)([A-Za-z]*)', s)
    if m:
        return (int(m.group(1)), m.group(2))
    return (9999, s)

mapping_summary = {}
for i in range(1, 171):
    sec_str = str(i)
    rels = base_map.get(sec_str, [])
    if not rels:
        mapping_summary[sec_str] = None
    elif len(rels) == 1:
        mapping_summary[sec_str] = str(rels[0]['b_sec']).strip()
    else:
        # Multiple IEA sections
        # Deduplicate while preserving order or sorting
        iea_secs = []
        for r in rels:
            s = str(r['b_sec']).strip()
            if s not in iea_secs:
                iea_secs.append(s)
        # Sort logically
        iea_secs.sort(key=sort_key)
        mapping_summary[sec_str] = ", ".join(iea_secs)

for i in range(1, 171):
    sec_str = str(i)
    val = mapping_summary[sec_str]
    print(f"BSA {sec_str:3s} -> IEA {val}")
