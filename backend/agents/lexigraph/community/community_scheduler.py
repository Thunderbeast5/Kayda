import logging
import threading
import time
from typing import Dict, Any

try:
    from .CommunityDetectionService import CommunityDetectionService
    from ..services.neo4j_service import Neo4jService
except ImportError:
    from community.CommunityDetectionService import CommunityDetectionService
    from services.neo4j_service import Neo4jService

logger = logging.getLogger("CommunityScheduler")


class CommunityScheduler:
    """
    Offline/Background Orchestrator for Neo4j GDS Leiden Community Detection.
    Ensures Leiden Community Detection is executed asynchronously during ingestion
    or batch graph updates without blocking real-time user query execution.
    """

    def __init__(self):
        self.neo4j_service = Neo4jService()
        self.detection_service = CommunityDetectionService(self.neo4j_service)
        self._is_running = False

    def run_detection_sync(self, seeded: bool = False) -> Dict[str, Any]:
        """Runs Leiden Community Detection synchronously."""
        logger.info("Executing synchronous Leiden Community Detection update...")
        return self.detection_service.execute_leiden_detection(seeded=seeded, force_reproject=True)

    def run_detection_async(self, seeded: bool = False):
        """Launches Leiden Community Detection in a background thread."""
        if self._is_running:
            logger.info("Leiden detection already running in background. Skipping duplicate trigger.")
            return

        def _worker():
            self._is_running = True
            try:
                logger.info("Background Leiden Community Detection thread started.")
                result = self.detection_service.execute_leiden_detection(seeded=seeded, force_reproject=True)
                logger.info(f"Background Leiden Detection finished successfully: {result}")
            except Exception as e:
                logger.error(f"Background Leiden Detection error: {e}")
            finally:
                self._is_running = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        logger.info("Background Leiden Detection thread dispatched.")


    def check_and_trigger_reclustering(self, force: bool = False, seeded: bool = True) -> Dict[str, Any]:
        """
        Checks delta threshold metrics (>=100 new sections or >=500 new case links)
        and automatically dispatches re-clustering if threshold is exceeded.
        """
        status = self.detection_service.check_reclustering_trigger()
        if force or status.get("should_trigger"):
            logger.info(f"Triggering automatic re-clustering: {status.get('reason')}")
            self.run_detection_async(seeded=seeded)
            return {"triggered": True, "reason": status.get("reason")}
        else:
            logger.info(f"Skipping automatic re-clustering: {status.get('reason')}")
            return {"triggered": False, "reason": status.get("reason")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scheduler = CommunityScheduler()
    print("Checking automatic re-clustering trigger status...")
    trigger_status = scheduler.check_and_trigger_reclustering(force=True, seeded=False)
    print("Trigger Status:", trigger_status)
