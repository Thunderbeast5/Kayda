from neo4j import GraphDatabase
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path('C:/Users/Ajinkya/Desktop/MootCourt/backend/.env'))
driver = GraphDatabase.driver(os.getenv('NEO4J_URI'), auth=(os.getenv('NEO4J_USER'), os.getenv('NEO4J_PASSWORD')))

with driver.session() as session:
    print('='*80)
    print('BNSS SECTIONS (Sample)')
    print('='*80)
    result = session.run('''
        MATCH (n:BNSSSection) 
        RETURN n.section AS sec, n.title AS title, n.bail_related AS bail
        ORDER BY toInteger(n.section)
        LIMIT 10
    ''')
    for r in result:
        bail_flag = '🔒' if r['bail'] else '  '
        print(f"{bail_flag} Section {r['sec']}: {r['title']}")
    
    print('\n' + '='*80)
    print('CrPC TO BNSS MAPPINGS (Sample)')
    print('='*80)
    result = session.run('''
        MATCH (c:CrPCSection)-[r:REPLACED_BY]->(b:BNSSSection)
        RETURN c.section AS crpc, b.section AS bnss, c.title AS title
        ORDER BY toInteger(c.section)
        LIMIT 10
    ''')
    for r in result:
        title_short = r['title'][:50] if r['title'] else ''
        print(f"CrPC {r['crpc']} → BNSS {r['bnss']}: {title_short}...")
    
    print('\n' + '='*80)
    print('BSA SECTIONS (Sample)')
    print('='*80)
    result = session.run('''
        MATCH (n:BSASection) 
        RETURN n.section AS sec, n.title AS title
        ORDER BY toInteger(n.section)
        LIMIT 10
    ''')
    for r in result:
        print(f"Section {r['sec']}: {r['title']}")
    
    print('\n' + '='*80)
    print('TOTAL COUNTS')
    print('='*80)
    
    for act in ['BNSS', 'CrPC', 'BSA', 'IEA']:
        result = session.run('''
            MATCH (n:LawSection {act: $act})
            RETURN count(n) AS count
        ''', act=act)
        count = result.single()['count']
        print(f'{act}: {count} sections')

driver.close()
print('\n✅ All nodes have complete data!')
print('In Neo4j Browser: Click the node label, then set Caption to "title" or "section"')
