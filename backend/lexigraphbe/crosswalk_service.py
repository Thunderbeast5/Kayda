"""
CrosswalkService: Authoritative mapping between IPC <-> BNS, BNSS <-> CrPC, and BSA <-> IEA.
Loads directly from Neo4j with automated validation and failsafe snapshot caching (Issue S-11).
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Specific clause selection rules for operative charging sections in BNS
# When an IPC section maps to a parent BNS section with subsections/clauses,
# this rule picks the operative punitive clause.
_BNS_OPERATIVE_CLAUSE_RULES: Dict[str, str] = {
    "323": "115(2)",   # Punishment for voluntarily causing hurt
    "324": "118(1)",   # Voluntarily causing hurt by dangerous weapons or means
    "325": "117(2)",   # Punishment for voluntarily causing grievous hurt
    "326": "118(2)",   # Voluntarily causing grievous hurt by dangerous weapons or means
    "504": "352",      # Intentional insult with intent to provoke breach of peace
    "506": "351(2)",   # Punishment for criminal intimidation
    "448": "329(4)",   # Punishment for house-trespass
    "452": "333",      # House-trespass after preparation for hurt, assault or wrongful restraint
    "420": "318(4)",   # Cheating and dishonestly inducing delivery of property
    "406": "316(2)",   # Punishment for criminal breach of trust
    "468": "336(3)",   # Forgery for purpose of cheating
    "465": "336(2)",   # Punishment for forgery
    "471": "340(2)",   # Using forged document as genuine
    "304A": "106(1)",  # Causing death by negligence
    "302": "103(1)",   # Punishment for murder
    "304": "105",      # Culpable homicide not amounting to murder
    "498A": "85",      # Cruelty by husband or relative of husband
    "304B": "80",      # Dowry death
    "379": "303(2)",   # Punishment for theft
    "380": "305",      # Theft in dwelling house
    "384": "308(2)",   # Punishment for extortion
}


class CrosswalkService:
    _instance: Optional["CrosswalkService"] = None

    def __init__(self):
        self.ipc_to_bns: Dict[str, List[str]] = {}
        self.bns_to_ipc: Dict[str, List[str]] = {}
        self.bnss_to_crpc: Dict[str, List[str]] = {}
        self.crpc_to_bnss: Dict[str, List[str]] = {}
        self.bsa_to_iea: Dict[str, List[str]] = {}
        self.iea_to_bsa: Dict[str, List[str]] = {}
        self.snapshot_path = Path(__file__).parent / "crosswalk_snapshot.json"
        self._load()

    @classmethod
    def get_instance(cls) -> "CrosswalkService":
        if cls._instance is None:
            cls._instance = CrosswalkService()
        return cls._instance

    def _load_from_snapshot(self) -> bool:
        if not self.snapshot_path.exists():
            return False
        try:
            with open(self.snapshot_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.ipc_to_bns = data.get("ipc_to_bns", {})
            self.bns_to_ipc = data.get("bns_to_ipc", {})
            self.bnss_to_crpc = data.get("bnss_to_crpc", {})
            self.crpc_to_bnss = data.get("crpc_to_bnss", {})
            self.bsa_to_iea = data.get("bsa_to_iea", {})
            self.iea_to_bsa = data.get("iea_to_bsa", {})
            logger.info("CrosswalkService: loaded from snapshot (%d IPC, %d BNSS, %d BSA)",
                        len(self.ipc_to_bns), len(self.bnss_to_crpc), len(self.bsa_to_iea))
            return True
        except Exception as e:
            logger.warning("CrosswalkService: failed loading snapshot: %s", e)
            return False

    def _load_from_neo4j(self) -> bool:
        try:
            from dotenv import load_dotenv
            for ep in [Path(__file__).parent.parent / ".env", Path("backend/.env"), Path(".env")]:
                if ep.exists():
                    load_dotenv(ep)
                    break
            uri = os.getenv("NEO4J_URI")
            user = os.getenv("NEO4J_USER") or os.getenv("NEO4J_USERNAME")
            pwd = os.getenv("NEO4J_PASSWORD")
            db = os.getenv("NEO4J_DATABASE", "neo4j")
            if not (uri and user and pwd):
                return False

            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(uri, auth=(user, pwd))
            with driver.session(database=db) as session:
                # 1. IPC -> BNS
                ipc_bns: Dict[str, List[str]] = {}
                bns_ipc: Dict[str, List[str]] = {}
                for r in session.run("MATCH (i:IPCSection)-[rel:REPLACED_BY]->(b:BNSSection) RETURN i.section AS ipc, b.section AS bns"):
                    i_sec = str(r["ipc"]).strip().upper()
                    b_sec = str(r["bns"]).strip().upper()
                    if i_sec and b_sec:
                        ipc_bns.setdefault(i_sec, []).append(b_sec)
                        bns_ipc.setdefault(b_sec, []).append(i_sec)

                # 2. BNSS <-> CrPC
                bnss_crpc: Dict[str, List[str]] = {}
                crpc_bnss: Dict[str, List[str]] = {}
                for r in session.run("MATCH (b:BNSSSection)-[rel:REPLACES|REPLACED_BY]-(c:CrPCSection) RETURN b.section AS bnss, c.section AS crpc"):
                    bnss_sec = str(r["bnss"]).strip().upper()
                    crpc_sec = str(r["crpc"]).strip().upper()
                    if bnss_sec and crpc_sec:
                        if crpc_sec not in bnss_crpc.get(bnss_sec, []):
                            bnss_crpc.setdefault(bnss_sec, []).append(crpc_sec)
                        if bnss_sec not in crpc_bnss.get(crpc_sec, []):
                            crpc_bnss.setdefault(crpc_sec, []).append(bnss_sec)

                # 3. BSA <-> IEA
                bsa_iea: Dict[str, List[str]] = {}
                iea_bsa: Dict[str, List[str]] = {}
                for r in session.run("MATCH (b:BSASection)-[rel:REPLACES|REPLACED_BY]-(i:IEASection) RETURN b.section AS bsa, i.section AS iea"):
                    bsa_sec = str(r["bsa"]).strip().upper()
                    iea_sec = str(r["iea"]).strip().upper()
                    if bsa_sec and iea_sec:
                        if iea_sec not in bsa_iea.get(bsa_sec, []):
                            bsa_iea.setdefault(bsa_sec, []).append(iea_sec)
                        if bsa_sec not in iea_bsa.get(iea_sec, []):
                            iea_bsa.setdefault(iea_sec, []).append(bsa_sec)

            driver.close()
            if len(ipc_bns) >= 500 and len(bnss_crpc) >= 500 and len(bsa_iea) >= 150:
                self.ipc_to_bns = ipc_bns
                self.bns_to_ipc = bns_ipc
                self.bnss_to_crpc = bnss_crpc
                self.crpc_to_bnss = crpc_bnss
                self.bsa_to_iea = bsa_iea
                self.iea_to_bsa = iea_bsa
                logger.info("CrosswalkService: successfully loaded all 3 crosswalks from Neo4j.")
                return True
            return False
        except Exception as e:
            logger.warning("CrosswalkService: Neo4j loading error: %s", e)
            return False

    def _load(self):
        # Prefer snapshot for sub-second startup; fall back to live Neo4j
        if not self._load_from_snapshot():
            if not self._load_from_neo4j():
                logger.error("CrosswalkService: FAILED to load crosswalks from both snapshot and Neo4j!")

    def get_bns_for_ipc(self, ipc_section: str, prefer_clause: bool = True) -> Optional[str]:
        """Returns the primary operative BNS section for an IPC section."""
        clean = str(ipc_section).strip().upper().replace("SECTION ", "").replace("IPC_", "")
        if prefer_clause and clean in _BNS_OPERATIVE_CLAUSE_RULES:
            return _BNS_OPERATIVE_CLAUSE_RULES[clean]
        targets = self.ipc_to_bns.get(clean, [])
        if targets:
            return targets[0]
        return None

    def get_ipc_for_bns(self, bns_section: str) -> Optional[str]:
        """Returns the IPC equivalent for a BNS section."""
        clean = str(bns_section).strip().upper().replace("SECTION ", "").replace("BNS_", "")
        # Strip sub-clauses for base section lookup if needed e.g. 115(2) -> 115
        base = clean.split("(")[0]
        targets = self.bns_to_ipc.get(clean) or self.bns_to_ipc.get(base) or []
        if targets:
            return targets[0]
        return None

    def get_crpc_for_bnss(self, bnss_section: str) -> Optional[str]:
        clean = str(bnss_section).strip().upper().replace("SECTION ", "").replace("BNSS_", "")
        targets = self.bnss_to_crpc.get(clean, [])
        return ", ".join(targets) if targets else None

    def get_bnss_for_crpc(self, crpc_section: str) -> Optional[str]:
        clean = str(crpc_section).strip().upper().replace("SECTION ", "").replace("CRPC_", "")
        targets = self.crpc_to_bnss.get(clean, [])
        return ", ".join(targets) if targets else None

    def get_iea_for_bsa(self, bsa_section: str) -> Optional[str]:
        clean = str(bsa_section).strip().upper().replace("SECTION ", "").replace("BSA_", "")
        targets = self.bsa_to_iea.get(clean, [])
        return ", ".join(targets) if targets else None

    def get_bsa_for_iea(self, iea_section: str) -> Optional[str]:
        clean = str(iea_section).strip().upper().replace("SECTION ", "").replace("IEA_", "")
        targets = self.iea_to_bsa.get(clean, [])
        return ", ".join(targets) if targets else None
