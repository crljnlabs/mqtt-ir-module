"""
Background service that syncs the Flipper-IRDB repository index into the local SQLite DB.

Strategy:
  1. Fetch the full file tree from the GitHub Trees API (one request, returns all paths + SHAs).
  2. Compare SHAs against already-stored entries to find new/changed/deleted files.
  3. Download only new/changed .ir files in parallel batches.
  4. Parse each file and store category/brand/model/buttons in marketplace_remotes + marketplace_buttons.

The sync runs in a daemon thread so it never blocks the FastAPI server.
"""
import logging
import socket
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests

from .ir_file_parser import parse_ir_file

logger = logging.getLogger(__name__)

_REPO = "Lucaslhm/Flipper-IRDB"
_BRANCH = "main"
_TREES_URL = f"https://api.github.com/repos/{_REPO}/git/trees/{_BRANCH}?recursive=1"
_RAW_BASE = f"https://raw.githubusercontent.com/{_REPO}/{_BRANCH}/"

# Directories to exclude from the index
_EXCLUDED_PREFIXES = ("_Converted_/",)

_DOWNLOAD_RETRIES = 3
_RETRY_BACKOFF = (2, 4)  # seconds before 2nd and 3rd attempts

# Sync retry config when connectivity fails
_SYNC_RETRY_DELAYS = (5 * 60, 10 * 60, 20 * 60, 40 * 60)  # 5 min, 10 min, 20 min, 40 min


class GitHubMarketplaceIndex:
    def __init__(self, database: Any) -> None:
        self._db = database
        self._lock = threading.Lock()
        self._running = False
        self._retry_count = 0
        self._status: Dict[str, Any] = {
            "status": "idle",
            "last_synced": None,
            "error": None,
            "total": 0,
            "done": 0,
        }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._status)

    def auto_sync(self) -> None:
        """Trigger an incremental sync on startup.

        Always runs because the SHA comparison in _run_sync makes it cheap:
        only new or changed files are downloaded. This also recovers from
        interrupted syncs that left the index incomplete.
        """
        try:
            self.trigger_sync()
            logger.info("Marketplace auto-sync started")
        except Exception as exc:
            logger.error(f"Marketplace auto-sync failed to start: {exc}")

    def trigger_sync(self) -> bool:
        """Start a background sync. Returns False if a sync is already running."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._status = {
                "status": "running",
                "last_synced": None,
                "error": None,
                "total": 0,
                "done": 0,
            }

        thread = threading.Thread(target=self._sync_worker, daemon=True, name="marketplace-sync")
        thread.start()
        return True

    def _sync_worker(self) -> None:
        try:
            self._run_sync()
        except Exception as exc:
            logger.error(f"Marketplace sync failed: {exc}")
            with self._lock:
                self._status["status"] = "error"
                self._status["error"] = str(exc)
                self._running = False
            self._schedule_retry()

    def _check_connectivity(self) -> bool:
        """DNS probe for raw.githubusercontent.com before batch downloads."""
        try:
            socket.getaddrinfo("raw.githubusercontent.com", 443, socket.AF_INET, socket.SOCK_STREAM)
            return True
        except socket.gaierror:
            return False

    def _schedule_retry(self) -> None:
        """Schedule a sync retry with exponential backoff. Gives up after all delays are exhausted."""
        idx = self._retry_count
        if idx >= len(_SYNC_RETRY_DELAYS):
            logger.error("Marketplace sync: max retries exhausted, giving up until next startup")
            return

        delay = _SYNC_RETRY_DELAYS[idx]
        self._retry_count += 1
        logger.info(
            f"Marketplace sync: retry {self._retry_count}/{len(_SYNC_RETRY_DELAYS)} "
            f"scheduled in {delay // 60} min"
        )
        thread = threading.Thread(
            target=self._retry_worker,
            daemon=True,
            args=(delay,),
            name=f"marketplace-retry-{self._retry_count}",
        )
        thread.start()

    def _retry_worker(self, delay: int) -> None:
        time.sleep(delay)
        with self._lock:
            if self._running:
                return  # a manual trigger happened in the meantime
        self.trigger_sync()

    def _run_sync(self) -> None:
        logger.info("Marketplace sync: fetching GitHub tree")

        # Step 1 — fetch the full repo tree (single API request)
        resp = requests.get(
            _TREES_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"GitHub Trees API returned {resp.status_code}: {resp.text[:200]}")

        response_data = resp.json()
        tree = response_data.get("tree", [])

        if response_data.get("truncated"):
            logger.warning("GitHub Trees API returned truncated result — fetching per-category subtrees")
            tree = self._fetch_tree_by_subtrees()

        # Step 2 — filter to valid .ir files with exactly 3 path segments (category/brand/file.ir)
        ir_files = [
            item for item in tree
            if item.get("type") == "blob"
            and item.get("path", "").endswith(".ir")
            and not any(item["path"].startswith(p) for p in _EXCLUDED_PREFIXES)
            and len(item["path"].split("/")) == 3
        ]

        logger.info(f"Marketplace sync: found {len(ir_files)} .ir files in repo")

        # Step 3 — compare with local index
        existing: Dict[str, str] = {
            row["path"]: row["sha"]
            for row in self._db.marketplace.list_paths_and_shas()
        }
        repo_paths = {f["path"] for f in ir_files}
        to_update = [f for f in ir_files if existing.get(f["path"]) != f["sha"]]
        to_delete = [p for p in existing if p not in repo_paths]

        logger.info(
            f"Marketplace sync: {len(to_update)} to update, "
            f"{len(to_delete)} to delete, {len(ir_files) - len(to_update)} unchanged"
        )

        with self._lock:
            self._status["total"] = len(to_update)
            self._status["done"] = 0

        # Step 4 — delete removed files
        if to_delete:
            self._db.marketplace.delete_by_paths(to_delete)

        # Step 5 — download and parse new/changed files in parallel
        failed = 0
        if to_update:
            if not self._check_connectivity():
                logger.warning(
                    f"Marketplace sync: DNS resolution failed for raw.githubusercontent.com — "
                    f"{len(to_update)} files pending, rescheduling"
                )
                with self._lock:
                    self._status["status"] = "idle"
                    self._status["error"] = "DNS resolution failed — sync rescheduled"
                    self._running = False
                self._schedule_retry()
                return

            with ThreadPoolExecutor(max_workers=10, thread_name_prefix="mkt-dl") as executor:
                futures = {executor.submit(self._fetch_file, item): item for item in to_update}
                for future in as_completed(futures):
                    item = futures[future]
                    try:
                        entry = future.result()
                        if entry:
                            self._db.marketplace.upsert(**entry)
                    except Exception as exc:
                        failed += 1
                        logger.warning(f"Failed to fetch {item.get('path')}: {exc}")
                    finally:
                        with self._lock:
                            self._status["done"] += 1

        if failed:
            logger.warning(f"Marketplace sync: {failed}/{len(to_update)} files failed to download")

        self._retry_count = 0
        with self._lock:
            self._status["status"] = "idle"
            self._status["last_synced"] = time.time()
            self._status["error"] = None
            self._running = False

        logger.info(f"Marketplace sync: complete ({failed} download failures)")

    def _fetch_tree_by_subtrees(self) -> List[Dict]:
        """Fetch the complete file tree by fetching each top-level category subtree individually.

        Used as fallback when the recursive tree fetch is truncated by GitHub (>100k entries / >7MB).
        Makes one request per top-level directory instead of one recursive request.
        """
        root_resp = requests.get(
            f"https://api.github.com/repos/{_REPO}/git/trees/{_BRANCH}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=30,
        )
        if root_resp.status_code != 200:
            raise RuntimeError(f"GitHub Trees API (root) returned {root_resp.status_code}: {root_resp.text[:200]}")

        root_data = root_resp.json()
        category_dirs = [
            item for item in root_data.get("tree", [])
            if item.get("type") == "tree"
            and not any(item["path"].startswith(p.rstrip("/")) for p in _EXCLUDED_PREFIXES)
        ]

        logger.info(f"Marketplace sync: fetching {len(category_dirs)} category subtrees")

        all_blobs: List[Dict] = []
        for category_dir in category_dirs:
            category = category_dir["path"]
            sub_resp = requests.get(
                f"https://api.github.com/repos/{_REPO}/git/trees/{category_dir['sha']}?recursive=1",
                headers={"Accept": "application/vnd.github+json"},
                timeout=30,
            )
            if sub_resp.status_code != 200:
                logger.warning(f"Failed to fetch subtree for category '{category}': {sub_resp.status_code}")
                continue

            sub_data = sub_resp.json()
            if sub_data.get("truncated"):
                logger.warning(f"Subtree for category '{category}' is also truncated — skipping")
                continue

            for item in sub_data.get("tree", []):
                if item.get("type") == "blob":
                    blob = dict(item)
                    blob["path"] = f"{category}/{item['path']}"
                    all_blobs.append(blob)

        logger.info(f"Marketplace sync: fetched {len(all_blobs)} blobs via subtree strategy")
        return all_blobs

    def _fetch_file(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Download and parse a single .ir file. Returns the entry dict or None on failure."""
        path = item["path"]
        url = _RAW_BASE + urllib.parse.quote(path)

        last_exc: Exception = RuntimeError("unreachable")
        for attempt in range(_DOWNLOAD_RETRIES):
            if attempt:
                time.sleep(_RETRY_BACKOFF[attempt - 1])
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                break
            except Exception as exc:
                last_exc = exc
        else:
            raise last_exc

        parts = path.split("/")
        category = parts[0]
        brand = parts[1]
        model = parts[2].removesuffix(".ir").replace("_", " ")

        buttons = parse_ir_file(resp.text)

        return {
            "source": "flipper-irdb",
            "path": path,
            "category": category,
            "brand": brand,
            "model": model,
            "sha": item["sha"],
            "buttons": buttons,
        }
