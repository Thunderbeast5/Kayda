import csv
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from neo4j import GraphDatabase

from .statute_repository import StatuteRepository


class IPC2BNSMapper:
    """
    Bidirectional IPC ↔ BNS statutory mapper.
    Uses Neo4j for mapping lookups, falling back to StatuteRepository singleton for instant in-memory lookups.
    """

    def __init__(self, csv_path: Optional[str] = None):
        self.neo4j_uri = os.getenv("NEO4J_URI")
        self.neo4j_user = os.getenv("NEO4J_USER")
        self.neo4j_password = os.getenv("NEO4J_PASSWORD")
        self.driver = None

        if self.neo4j_uri and self.neo4j_user and self.neo4j_password:
            try:
                self.driver = GraphDatabase.driver(self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password))
            except Exception as e:
                print(f"Failed to connect to Neo4j in IPC2BNSMapper: {e}")

        if not csv_path:
            repo = StatuteRepository.get_instance()
            self.ipc_to_bns = repo.get_ipc_to_bns_map()
            self.bns_to_ipc = repo.get_bns_to_ipc_map()
        else:
            self.ipc_to_bns = {}
            self.bns_to_ipc = {}
            self._load_mapping_table(csv_path)

    def _load_mapping_table(self, custom_path: Optional[str] = None):
        candidate_paths = [
            Path("backend/lexigraphbe/ipc2bns_clean.csv"),
            Path("ipc2bns_clean.csv"),
            Path("c:/MootCourt/backend/lexigraphbe/ipc2bns_clean.csv"),
        ]
        if custom_path:
            candidate_paths.insert(0, Path(custom_path))

        target_path = None
        for p in candidate_paths:
            if p.exists():
                target_path = p
                break

        if not target_path:
            return

        try:
            with open(target_path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    ipc_sec = (row.get("IPC_Section") or "").strip().upper()
                    bns_clean = (row.get("BNS_Section_Clean") or "").strip().upper()
                    bns_raw = (row.get("BNS_Section_Raw") or "").strip()
                    ipc_title = (row.get("IPC_Title") or "").strip()
                    bns_title = (row.get("BNS_Title") or "").strip()
                    parent_bns = (row.get("ParentSection") or "").strip()

                    entry = {
                        "ipc_section": ipc_sec,
                        "ipc_title": ipc_title,
                        "bns_section_clean": bns_clean,
                        "bns_section_raw": bns_raw,
                        "bns_title": bns_title,
                        "parent_bns_section": parent_bns,
                    }

                    if ipc_sec:
                        self.ipc_to_bns[ipc_sec] = entry

                    if bns_clean and bns_clean != "REMOVED":
                        self.bns_to_ipc[bns_clean] = entry
                    if parent_bns and parent_bns not in self.bns_to_ipc:
                        self.bns_to_ipc[parent_bns] = entry

        except Exception:
            pass

    def get_bns_equivalent(self, ipc_section: str) -> Optional[Dict[str, str]]:
        """Given IPC section e.g. '498A', returns BNS equivalent dict using Neo4j (fallback to CSV)."""
        clean_key = ipc_section.replace("IPC", "").replace("_", "").strip().upper()

        if self.driver:
            try:
                with self.driver.session() as session:
                    query = """
                    MATCH (i:LawSection {act: 'IPC', section: $ipc_sec})-[r:REPLACED_BY]->(b:LawSection {act: 'BNS'})
                    RETURN b.section AS bns_section_clean, b.title AS bns_title
                    LIMIT 1
                    """
                    result = session.run(query, ipc_sec=clean_key).data()
                    if result:
                        record = result[0]
                        return {
                            "bns_section_clean": record.get("bns_section_clean"),
                            "bns_title": record.get("bns_title")
                        }
            except Exception as e:
                print(f"Neo4j query failed in get_bns_equivalent: {e}")

        return self.ipc_to_bns.get(clean_key)

    def get_ipc_equivalent(self, bns_section: str) -> Optional[Dict[str, str]]:
        """Given BNS section e.g. '85' or '318(4)', returns IPC equivalent dict using Neo4j (fallback to CSV)."""
        clean_key = bns_section.replace("BNS", "").replace("_", "").strip().upper()

        if self.driver:
            try:
                with self.driver.session() as session:
                    query = """
                    MATCH (i:LawSection {act: 'IPC'})-[r:REPLACED_BY]->(b:LawSection {act: 'BNS', section: $bns_sec})
                    RETURN i.section AS ipc_section, i.title AS ipc_title
                    LIMIT 1
                    """
                    result = session.run(query, bns_sec=clean_key).data()
                    if result:
                        record = result[0]
                        return {
                            "ipc_section": record.get("ipc_section"),
                            "ipc_title": record.get("ipc_title")
                        }
            except Exception as e:
                print(f"Neo4j query failed in get_ipc_equivalent: {e}")

        return self.bns_to_ipc.get(clean_key)
