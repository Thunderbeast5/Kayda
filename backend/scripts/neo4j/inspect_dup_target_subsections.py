import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
ENV_PATH = BASE_DIR / "backend" / ".env" if (BASE_DIR / "backend" / ".env").exists() else BASE_DIR / ".env"
load_dotenv(ENV_PATH)

driver = GraphDatabase.driver(os.getenv("NEO4J_URI"), auth=(os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")))

target_ids = ["BNS_8(6)", "BNS_189(2)", "BNS_189(5)", "BNS_70(2)"]

print("=" * 80)
print(" VERIFYING DUPLICATE-TARGET BNS SUBSECTION NODES IN NEO4J")
print("=" * 80 + "\n")

with driver.session() as s:
    for sid in target_ids:
        # Child node properties
        node_res = s.run("""
            MATCH (n:LawSection {id: $id})
            RETURN properties(n) AS props
        """, id=sid).single()
        props = node_res["props"] if node_res else {}

        # Parent node properties
        parent_res = s.run("""
            MATCH (p:LawSection)-[:HAS_SUBSECTION]->(n:LawSection {id: $id})
            RETURN p.id AS parent_id, p.title AS parent_title, p.description AS parent_desc
        """, id=sid).single()

        # Keywords (inherited vs direct)
        kw_res = s.run("""
            MATCH (n:LawSection {id: $id})-[r:HAS_KEYWORD]->(k:Keyword)
            RETURN k.name AS name, r.inherited AS inherited, r.inherited_from AS from_id
        """, id=sid).data()

        # Punishments (inherited vs direct)
        p_res = s.run("""
            MATCH (n:LawSection {id: $id})-[r:HAS_PUNISHMENT]->(p:Punishment)
            RETURN p.description AS desc, r.inherited AS inherited, r.inherited_from AS from_id
        """, id=sid).data()

        # Inbound IPC mapping edges
        ipc_res = s.run("""
            MATCH (i:LawSection)-[r:REPLACED_BY]->(n:LawSection {id: $id})
            RETURN i.id AS ipc_id, r.ipc_title AS rel_title
        """, id=sid).data()

        print(f"--- NODE: {sid} ---")
        print(f"  * Node Title (.title)      : '{props.get('title')}'")
        if parent_res:
            print(f"  * Parent ID & Title        : {parent_res['parent_id']} -> '{parent_res['parent_title']}'")
            title_inherited = props.get('title') == parent_res['parent_title']
            print(f"  * Title Inherited?         : {'YES' if title_inherited else 'NO (Canonical BNS Bare Act Subsection Title)'}")
        
        print(f"  * Node Description         : '{props.get('description') or '(Handled via Parent Section / Ingestion)'}'")
        
        kw_inherited_count = sum(1 for k in kw_res if k.get('inherited'))
        print(f"  * Keywords Connected       : Total={len(kw_res)} (Inherited={kw_inherited_count}, Direct={len(kw_res) - kw_inherited_count})")
        if kw_res:
            sample_kw = kw_res[0]
            print(f"    - Sample Keyword        : '{sample_kw['name']}' [inherited={sample_kw.get('inherited')}, from={sample_kw.get('from_id')}]")

        p_inherited_count = sum(1 for p in p_res if p.get('inherited'))
        print(f"  * Punishments Connected    : Total={len(p_res)} (Inherited={p_inherited_count}, Direct={len(p_res) - p_inherited_count})")
        if p_res:
            sample_p = p_res[0]
            print(f"    - Sample Punishment     : '{sample_p['desc']}' [inherited={sample_p.get('inherited')}, from={sample_p.get('from_id')}]")

        print(f"  * Inbound IPC Relationships : {[{r['ipc_id']: r['rel_title']} for r in ipc_res]}")
        print()

driver.close()
