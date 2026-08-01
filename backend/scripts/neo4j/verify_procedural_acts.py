"""
Verify and add specific labels to BNSS, CrPC, IEA, BSA sections for easier visibility
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent.parent / ".env")

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

print("Checking sections in database...")
with driver.session() as session:
    # Check what's in the database
    result = session.run("""
        MATCH (n:LawSection) 
        WHERE n.act IN ['BNSS', 'CrPC', 'IEA', 'BSA']
        RETURN n.act AS act, count(n) AS count
        ORDER BY act
    """)
    
    print("\n=== Current Section Counts ===")
    for record in result:
        print(f"{record['act']}: {record['count']} sections")
    
    # Add specific labels for easier querying
    print("\n=== Adding specific node labels ===")
    
    # Add BNSSSection label
    result = session.run("""
        MATCH (n:LawSection {act: 'BNSS'})
        SET n:BNSSSection
        RETURN count(n) AS count
    """)
    count = result.single()['count']
    print(f"✓ Added BNSSSection label to {count} nodes")
    
    # Add CrPCSection label
    result = session.run("""
        MATCH (n:LawSection {act: 'CrPC'})
        SET n:CrPCSection
        RETURN count(n) AS count
    """)
    count = result.single()['count']
    print(f"✓ Added CrPCSection label to {count} nodes")
    
    # Add BSASection label
    result = session.run("""
        MATCH (n:LawSection {act: 'BSA'})
        SET n:BSASection
        RETURN count(n) AS count
    """)
    count = result.single()['count']
    print(f"✓ Added BSASection label to {count} nodes")
    
    # Add IEASection label
    result = session.run("""
        MATCH (n:LawSection {act: 'IEA'})
        SET n:IEASection
        RETURN count(n) AS count
    """)
    count = result.single()['count']
    print(f"✓ Added IEASection label to {count} nodes")
    
    print("\n=== Sample nodes from each act ===")
    
    # Show sample BNSS nodes
    result = session.run("""
        MATCH (n:BNSSSection)
        RETURN n.section AS section, n.title AS title
        ORDER BY toInteger(n.section)
        LIMIT 3
    """)
    print("\nBNSS (first 3):")
    for record in result:
        print(f"  Section {record['section']}: {record['title'][:60]}...")
    
    # Show sample CrPC nodes
    result = session.run("""
        MATCH (n:CrPCSection)
        RETURN n.section AS section, n.title AS title
        ORDER BY toInteger(n.section)
        LIMIT 3
    """)
    print("\nCrPC (first 3):")
    for record in result:
        print(f"  Section {record['section']}: {record['title'][:60]}...")
    
    # Show sample BSA nodes
    result = session.run("""
        MATCH (n:BSASection)
        RETURN n.section AS section, n.title AS title
        ORDER BY toInteger(n.section)
        LIMIT 3
    """)
    print("\nBSA (first 3):")
    for record in result:
        print(f"  Section {record['section']}: {record['title'][:60]}...")
    
    # Show sample IEA nodes
    result = session.run("""
        MATCH (n:IEASection)
        RETURN n.section AS section, n.title AS title
        ORDER BY toInteger(n.section)
        LIMIT 3
    """)
    print("\nIEA (first 3):")
    for record in result:
        print(f"  Section {record['section']}: {record['title'][:60]}...")
    
    # Check mappings
    print("\n=== Mapping Relationships ===")
    
    result = session.run("""
        MATCH (c:CrPCSection)-[r:REPLACED_BY]->(b:BNSSSection)
        RETURN count(r) AS count
    """)
    count = result.single()['count']
    print(f"CrPC → BNSS mappings: {count}")
    
    result = session.run("""
        MATCH (i:IEASection)-[r:REPLACED_BY]->(b:BSASection)
        RETURN count(r) AS count
    """)
    count = result.single()['count']
    print(f"IEA → BSA mappings: {count}")

driver.close()
print("\n✅ Done! You should now see BNSSSection, CrPCSection, BSASection, and IEASection labels in Neo4j Browser.")
