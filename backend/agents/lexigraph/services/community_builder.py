import os
import sys
import time
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from neo4j import GraphDatabase

# Set up paths and sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(BASE_DIR / ".env")

sys.path.append(str(BASE_DIR))

# Import LLM config helper
try:
    from config.llm_config import get_llm
except ModuleNotFoundError:
    from agents.config.llm_config import get_llm

NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USER = os.getenv("NEO4J_USER")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")


COMMUNITY_DEFS = {
    "women_offences": {
        "name": "Women Offences",
        "description": "Offences relating to sexual assault, dowry, domestic violence, rape, and cruelty to married women.",
        "keywords": ["rape", "dowry", "cruelty", "modesty", "marriage", "husband", "wife", "harassment", "women"],
        "category": "Offences against Human Body"
    },
    "children_offences": {
        "name": "Children Offences",
        "description": "Offences relating to kidnapping, abduction, and assault of minors or children.",
        "keywords": ["child", "minor", "children", "kidnapping", "infant"],
        "category": "Offences against Human Body"
    },
    "property_offences": {
        "name": "Property Offences",
        "description": "Offences relating to theft, robbery, burglary, mischief, extortion, and trespass.",
        "keywords": ["theft", "robbery", "burglary", "extortion", "trespass", "mischief"],
        "category": "Offences against Property"
    },
    "cyber_crime": {
        "name": "Cyber Crime",
        "description": "Offences committed using computer systems, networks, and electronic devices.",
        "keywords": ["cyber", "computer", "hacking", "electronic", "internet", "information technology"],
        "category": "Cyber Crime"
    },
    "financial_crime": {
        "name": "Financial Crime",
        "description": "Offences relating to forgery, counterfeiting, cheating, tax fraud, and currency manipulation.",
        "keywords": ["forgery", "counterfeit", "cheating", "fraud", "coin", "currency"],
        "category": "Financial Crime"
    },
    "human_body_offences": {
        "name": "Offences Against Human Body",
        "description": "Offences relating to homicide, murder, hurt, wrongful restraint, and causing death by negligence.",
        "keywords": ["murder", "homicide", "negligence", "hurt", "assault", "kidnap", "injury", "death"],
        "category": "Offences against Human Body"
    },
    "evidence_law": {
        "name": "Evidence Law",
        "description": "Provisions governing the relevancy, proof, and admissibility of facts and witness statements.",
        "keywords": ["evidence", "witness", "confession", "dying declaration", "admissibility"],
        "category": "Evidence"
    },
    "criminal_procedure": {
        "name": "Criminal Procedure",
        "description": "Provisions governing police processes, arrests, summonses, justice administration, and public order.",
        "keywords": ["court", "judge", "police", "arrest", "summons", "procedure", "justice"],
        "category": "Procedure"
    },
    "constitutional_rights": {
        "name": "Constitutional Rights",
        "description": "Fundamental constitutional protections, personal liberty, equality, and state directives.",
        "keywords": ["constitution", "fundamental rights", "article", "liberty", "equality"],
        "category": "Constitutional"
    },
    "general_offences": {
        "name": "General Offences",
        "description": "General provisions, fallbacks, miscellaneous public order offences, and exceptions.",
        "keywords": ["general", "provisions", "offences", "fallback", "public order"],
        "category": "General"
    }
}


def classify_section(act: str, section: str, title: str, description: str, category: str) -> str:
    """Classifies a section into a community using rule-based classification."""
    act_upper = act.upper()
    title_lower = title.lower()
    desc_lower = description.lower()
    cat_lower = (category or "").lower()

    # 1. Constitutional Rights
    if act_upper == "COI" or "constitution" in title_lower or "article" in title_lower:
        return "constitutional_rights"

    # 2. Evidence Law
    if act_upper == "IEA" or "evidence" in desc_lower or "witness" in desc_lower:
        return "evidence_law"

    # 3. Women Offences
    for w in ["rape", "dowry", "cruelty", "modesty", "marriage", "husband", "wife", "harassment", "women"]:
        if w in title_lower or w in desc_lower or "women" in cat_lower:
            return "women_offences"

    # 4. Children Offences
    for w in ["child", "minor", "children", "kidnapping a minor", "kidnaps minor"]:
        if w in title_lower or w in desc_lower or "children" in cat_lower:
            return "children_offences"

    # 5. Cyber Crime
    for w in ["cyber", "computer", "hacking", "electronic record", "information technology"]:
        if w in title_lower or w in desc_lower:
            return "cyber_crime"

    # 6. Financial Crime
    for w in ["forgery", "counterfeit", "cheating", "fraud", "coin", "currency", "financial"]:
        if w in title_lower or w in desc_lower:
            return "financial_crime"

    # 7. Property Offences
    if "property" in cat_lower or any(p in title_lower or p in desc_lower for p in ["theft", "robbery", "burglary", "extortion", "trespass", "mischief"]):
        return "property_offences"

    # 8. Offences Against Human Body
    if "human body" in cat_lower or any(h in title_lower or h in desc_lower for h in ["murder", "homicide", "negligence", "hurt", "assault", "kidnap", "injury", "death"]):
        return "human_body_offences"

    # 9. Criminal Procedure
    if "justice" in cat_lower or "order" in cat_lower or any(c in title_lower or c in desc_lower for c in ["court", "judge", "police", "arrest", "summons", "public servant"]):
        return "criminal_procedure"

    # 10. General fallbacks
    if "general" in cat_lower:
        return "general_offences"

    return "general_offences"


def build_communities():
    if not all([NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD]):
        print("[community_builder] Error: Missing Neo4j credentials.")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    
    with driver.session(database=NEO4J_DATABASE) as session:
        # Create constraint
        print("[community_builder] Creating Community unique constraint...")
        session.run("CREATE CONSTRAINT community_unique IF NOT EXISTS FOR (c:Community) REQUIRE c.community_id IS UNIQUE")
        
        # Create Community nodes
        print("[community_builder] Ingesting Community nodes...")
        for cid, details in COMMUNITY_DEFS.items():
            session.run("""
                MERGE (c:Community {community_id: $community_id})
                SET c.name = $name,
                    c.description = $description,
                    c.keywords = $keywords,
                    c.category = $category,
                    c.created_at = $created_at
            """, community_id=cid, name=details["name"], description=details["description"],
               keywords=details["keywords"], category=details["category"], created_at=datetime.utcnow().isoformat())

        # Retrieve all BNS & IEA & COI sections to classify first (to establish ground truths)
        print("[community_builder] Classifying BNS/IEA/COI sections...")
        res = session.run("""
            MATCH (n:LawSection)
            WHERE n.act IN ['BNS', 'IEA', 'COI']
            RETURN id(n) as node_id, n.act as act, n.section as section, 
                   n.title as title, n.description as description, n.category as category
        """)
        
        bns_assignments = {} # section -> community
        for r in res:
            assigned = classify_section(r["act"], r["section"], r["title"] or "", r["description"] or "", r["category"] or "")
            bns_assignments[f"{r['act']}_{r['section']}"] = assigned
            session.run("""
                MATCH (n) WHERE id(n) = $node_id
                MATCH (c:Community {community_id: $community_id})
                MERGE (n)-[:BELONGS_TO]->(c)
            """, node_id=r["node_id"], community_id=assigned)
            
        print(f"[community_builder] Classified {len(bns_assignments)} non-IPC sections.")

        # Classify IPC sections based on BNS successor mappings if available, otherwise rules
        print("[community_builder] Classifying IPC sections...")
        res_ipc = session.run("""
            MATCH (n:LawSection {act: 'IPC'})
            RETURN id(n) as node_id, n.section as section, n.title as title, n.description as description
        """)
        
        ipc_count = 0
        for r in res_ipc:
            # Check replacements mappings
            map_res = session.run("""
                MATCH (n:LawSection {act: 'IPC', section: $section})-[r:REPLACED_BY|REPLACES]-(other:LawSection {act: 'BNS'})
                RETURN other.section as bns_section
                LIMIT 1
            """, section=r["section"])
            
            bns_sec = None
            for row in map_res:
                bns_sec = row["bns_section"]
                
            assigned = None
            if bns_sec and f"BNS_{bns_sec}" in bns_assignments:
                assigned = bns_assignments[f"BNS_{bns_sec}"]
            else:
                assigned = classify_section("IPC", r["section"], r["title"] or "", r["description"] or "", "")
                
            session.run("""
                MATCH (n) WHERE id(n) = $node_id
                MATCH (c:Community {community_id: $community_id})
                MERGE (n)-[:BELONGS_TO]->(c)
            """, node_id=r["node_id"], community_id=assigned)
            ipc_count += 1
            
        print(f"[community_builder] Classified {ipc_count} IPC sections.")

        # Recalculate node counts and edge counts for metadata
        print("[community_builder] Updating community metadata counts...")
        for cid in COMMUNITY_DEFS.keys():
            # Node count
            node_count = session.run("""
                MATCH (:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                RETURN count(*) as c
            """, community_id=cid).single()["c"]
            
            # Edge count
            edge_count = session.run("""
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                MATCH (n)-[r]-()
                RETURN count(DISTINCT r) as c
            """, community_id=cid).single()["c"]
            
            session.run("""
                MATCH (c:Community {community_id: $community_id})
                SET c.node_count = $node_count,
                    c.edge_count = $edge_count
            """, community_id=cid, node_count=node_count, edge_count=edge_count)

        # Generate summaries using the LLM
        print("[community_builder] Generating Community Summaries using LLM...")
        llm = get_llm(temperature=0.2)
        
        for cid, details in COMMUNITY_DEFS.items():
            print(f"  Summarizing community: {details['name']}...")
            
            # Fetch sections in this community
            sec_rows = session.run("""
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                RETURN n.act as act, n.section as section, n.title as title, n.description as description
                LIMIT 15
            """, community_id=cid)
            sections_list = [f"{row['act']} {row['section']} - {row['title']}: {row['description']}" for row in sec_rows]
            
            # Fetch connected constitutional articles
            const_rows = session.run("""
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                MATCH (n)-[:PROTECTED_BY]->(a:ConstitutionalArticle)
                RETURN DISTINCT a.article as article, a.title as title
            """, community_id=cid)
            articles = [f"{row['article']} ({row['title']})" for row in const_rows]

            # Fetch connected evidence types
            ev_rows = session.run("""
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                MATCH (n)-[:SUPPORTED_BY]->(et:EvidenceType)
                RETURN DISTINCT et.name as name
            """, community_id=cid)
            evidence = [row["name"] for row in ev_rows]

            # Fetch connected legal principles
            lp_rows = session.run("""
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                MATCH (lp:LegalPrinciple)-[:APPLIES_TO]->(n)
                RETURN DISTINCT lp.name as name
            """, community_id=cid)
            principles = [row["name"] for row in lp_rows]

            # Fetch connected SC cases
            sc_rows = session.run("""
                MATCH (n:LawSection)-[:BELONGS_TO]->(c:Community {community_id: $community_id})
                MATCH (n)-[:INTERPRETED_BY]->(sc:SupremeCourtCase)
                RETURN DISTINCT sc.case_name as name
            """, community_id=cid)
            cases = [row["name"] for row in sc_rows]

            sections_info = "\n".join(sections_list)
            
            prompt = f"""
You are an expert legal annotator summarizing legal knowledge graph communities for Kayda AI.

Write a summary for the community: "{details['name']}".
Description: {details['description']}

Here are some example law sections in this community:
{sections_info}

Here are the connected graph elements:
Relevant Constitutional Articles: {", ".join(articles) if articles else "None"}
Relevant Evidence Types: {", ".join(evidence) if evidence else "None"}
Relevant Legal Principles: {", ".join(principles) if principles else "None"}
Relevant Supreme Court Cases: {", ".join(cases) if cases else "None"}

Please produce the summary in this exact format:
This community contains offences relating to <list of core criminal topics like rape, theft, murder, etc.>.

Important Sections: <comma-separated list of section numbers, e.g. 63, 66, 80>
Relevant Constitution: <comma-separated list of constitutional articles, e.g. Article 14, Article 21>
Relevant Evidence: <comma-separated list of evidence types, e.g. Witness Statement, Medical Report>
Relevant Legal Principles: <comma-separated list of principles, e.g. Burden of Proof, Mens Rea>
Relevant Supreme Court Cases: <comma-separated list of SC case names, e.g. Lalita Kumari>
"""
            try:
                response = llm.invoke(prompt)
                summary_text = response.content.strip()
                
                # Save to database
                session.run("""
                    MATCH (c:Community {community_id: $community_id})
                    SET c.summary = $summary
                """, community_id=cid, summary=summary_text)
                
            except Exception as e:
                print(f"    Error generating summary for {details['name']}: {e}")
                
        print("[community_builder] Success! All communities built, assignments completed, and summaries stored.")
        
    driver.close()


if __name__ == "__main__":
    build_communities()
