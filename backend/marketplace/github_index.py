"""
Background service that syncs IR remote databases into the local SQLite DB.

Strategy (per source):
  1. Fetch the latest commit SHA from GitHub (1 DNS lookup to api.github.com).
  2. Compare with the stored commit SHA — skip entirely if unchanged.
  3. Download the full repo tarball in one HTTPS request (1 DNS lookup).
  4. Extract .ir files in-memory; compute per-file git-blob SHA from content.
  5. Compare per-file SHAs against the local DB to find new/changed/deleted files.
  6. Parse only changed/new files; upsert to DB; delete removed entries.

This replaces the previous approach of downloading thousands of individual files in
parallel, which triggered one DNS lookup per file and caused DNS rate-limit failures
on environments with a filtering proxy (PiHole, router DNS, etc.).
"""
import hashlib
import io
import logging
import socket
import tarfile
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

from .ir_file_parser import parse_ir_file

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"

# Sync retry delays when connectivity fails: 5 min → 10 min → 20 min → 40 min
_SYNC_RETRY_DELAYS = (5 * 60, 10 * 60, 20 * 60, 40 * 60)


@dataclass
class RepoSource:
    name: str                                          # DB source tag, e.g. "flipper-irdb"
    repo: str                                          # "Owner/Repo"
    branch: str = "main"
    excluded_prefixes: tuple = field(default_factory=lambda: ("_Converted_/",))


# All configured sources — add a second repo here when needed.
_SOURCES: List[RepoSource] = [
    RepoSource(name="flipper-irdb", repo="Lucaslhm/Flipper-IRDB"),
]


def _git_blob_sha(content: str) -> str:
    """Compute the git blob SHA-1 for file content (identical to what GitHub reports)."""
    data = content.encode()
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


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
        """Trigger an incremental sync on startup."""
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
        """DNS probe for api.github.com before any network call."""
        try:
            socket.getaddrinfo("api.github.com", 443, socket.AF_INET, socket.SOCK_STREAM)
            return True
        except socket.gaierror:
            return False

    def _schedule_retry(self) -> None:
        """Schedule a sync retry with exponential backoff. Gives up after all delays."""
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

    # ------------------------------------------------------------------
    # Core sync
    # ------------------------------------------------------------------

    def _run_sync(self) -> None:
        if not self._check_connectivity():
            logger.warning("Marketplace sync: DNS resolution failed for api.github.com — rescheduling")
            with self._lock:
                self._status["status"] = "idle"
                self._status["error"] = "DNS resolution failed — sync rescheduled"
                self._running = False
            self._schedule_retry()
            return

        total_updated = 0
        total_deleted = 0

        for source in _SOURCES:
            updated, deleted = self._sync_source(source)
            total_updated += updated
            total_deleted += deleted

        self._retry_count = 0
        with self._lock:
            self._status["status"] = "idle"
            self._status["last_synced"] = time.time()
            self._status["error"] = None
            self._running = False

        logger.info(f"Marketplace sync: complete ({total_updated} updated, {total_deleted} deleted)")

    def _sync_source(self, source: RepoSource) -> tuple[int, int]:
        """Sync one source. Returns (updated_count, deleted_count)."""
        logger.info(f"Marketplace sync: checking {source.name} ({source.repo})")

        # Step 1 — get latest commit SHA (1 API call, 1 DNS lookup)
        commit_resp = requests.get(
            f"{_GITHUB_API}/repos/{source.repo}/commits/{source.branch}?per_page=1",
            headers={"Accept": "application/vnd.github+json"},
            timeout=30,
        )
        if commit_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub commits API returned {commit_resp.status_code} for {source.repo}: "
                f"{commit_resp.text[:200]}"
            )
        latest_sha = commit_resp.json()["sha"]

        # Step 2 — skip if repo hasn't changed since last sync
        meta_key = f"{source.name}:commit_sha"
        stored_sha = self._db.marketplace.get_meta(meta_key)
        if stored_sha == latest_sha:
            logger.info(f"Marketplace sync: {source.name} unchanged (commit {latest_sha[:8]}), skipping")
            return 0, 0

        logger.info(f"Marketplace sync: {source.name} changed ({latest_sha[:8]}), downloading tarball")

        # Step 3 — download full repo tarball (1 HTTPS request, 1 DNS lookup)
        tarball_resp = requests.get(
            f"{_GITHUB_API}/repos/{source.repo}/tarball/{source.branch}",
            headers={"Accept": "application/vnd.github+json"},
            timeout=120,
        )
        if tarball_resp.status_code != 200:
            raise RuntimeError(
                f"GitHub tarball API returned {tarball_resp.status_code} for {source.repo}"
            )

        tarball_size_kb = len(tarball_resp.content) // 1024
        logger.info(f"Marketplace sync: {source.name} tarball downloaded ({tarball_size_kb} KB)")

        # Step 4 — extract .ir files from tarball in-memory
        repo_files: Dict[str, str] = {}  # path -> content
        with tarfile.open(fileobj=io.BytesIO(tarball_resp.content), mode="r:gz") as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                # GitHub tarballs have a top-level dir: "Owner-Repo-{sha}/"
                parts = member.name.split("/")
                if len(parts) != 4:  # top-dir + category + brand + file.ir
                    continue
                relative_path = "/".join(parts[1:])  # strip top-level dir
                if not relative_path.endswith(".ir"):
                    continue
                if any(relative_path.startswith(p) for p in source.excluded_prefixes):
                    continue

                f = tf.extractfile(member)
                if f is None:
                    continue
                content = f.read().decode("utf-8", errors="replace")
                repo_files[relative_path] = content

        logger.info(f"Marketplace sync: {source.name} — {len(repo_files)} .ir files in tarball")

        # Step 5 — compute per-file SHAs and diff against DB (scoped to this source)
        repo_shas = {path: _git_blob_sha(content) for path, content in repo_files.items()}

        existing: Dict[str, str] = {
            row["path"]: row["sha"]
            for row in self._db.marketplace.list_paths_and_shas(source=source.name)
        }

        to_update = [p for p, sha in repo_shas.items() if existing.get(p) != sha]
        to_delete = [p for p in existing if p not in repo_shas]

        with self._lock:
            self._status["total"] = len(to_update)
            self._status["done"] = 0

        logger.info(
            f"Marketplace sync: {source.name} — {len(to_update)} to update, "
            f"{len(to_delete)} to delete, {len(repo_files) - len(to_update)} unchanged"
        )

        # Step 6 — delete removed entries
        if to_delete:
            self._db.marketplace.delete_by_paths(to_delete)

        # Step 7 — parse and upsert new/changed files
        for path in to_update:
            content = repo_files[path]
            parts = path.split("/")
            category = parts[0]
            brand = parts[1]
            model = parts[2].removesuffix(".ir").replace("_", " ")
            buttons = parse_ir_file(content)
            self._db.marketplace.upsert(
                source=source.name,
                path=path,
                category=category,
                brand=brand,
                model=model,
                sha=repo_shas[path],
                buttons=buttons,
            )
            with self._lock:
                self._status["done"] += 1

        # Step 8 — store new commit SHA so next sync can skip if unchanged
        self._db.marketplace.set_meta(meta_key, latest_sha)

        return len(to_update), len(to_delete)
