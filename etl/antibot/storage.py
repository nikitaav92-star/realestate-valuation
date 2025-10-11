"""Storage state management with rotation and verification."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

LOGGER = logging.getLogger(__name__)


@dataclass
class StorageStateMetadata:
    """Metadata for a storage state file."""
    
    path: Path
    created_at: float
    last_verified: Optional[float] = None
    is_valid: bool = True
    verification_failures: int = 0
    source: str = "local"  # local, s3, manual
    
    def is_fresh(self, max_age_seconds: float = 86400) -> bool:
        """Check if storage state is fresh enough to use.
        
        Parameters
        ----------
        max_age_seconds : float
            Maximum age in seconds (default: 24 hours)
            
        Returns
        -------
        bool
            True if state is fresh
        """
        age = time.time() - self.created_at
        return age < max_age_seconds
    
    def needs_verification(self, verify_interval: float = 3600) -> bool:
        """Check if state needs re-verification.
        
        Parameters
        ----------
        verify_interval : float
            Seconds between verifications (default: 1 hour)
            
        Returns
        -------
        bool
            True if verification is needed
        """
        if self.last_verified is None:
            return True
        return (time.time() - self.last_verified) > verify_interval


class StorageStateManager:
    """Manager for browser storage states with rotation."""
    
    def __init__(
        self,
        storage_dir: Path | str,
        *,
        max_age_seconds: float = 86400,
        verify_interval: float = 3600,
    ) -> None:
        """Initialize storage state manager.
        
        Parameters
        ----------
        storage_dir : Path | str
            Directory containing storage state files
        max_age_seconds : float
            Maximum age for storage states (default: 24 hours)
        verify_interval : float
            Seconds between verifications (default: 1 hour)
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_seconds = max_age_seconds
        self.verify_interval = verify_interval
        self.states: list[StorageStateMetadata] = []
        self._scan_storage_dir()
    
    def _scan_storage_dir(self) -> None:
        """Scan storage directory for state files."""
        self.states = []
        
        for path in self.storage_dir.glob("*.json"):
            try:
                stat = path.stat()
                metadata = StorageStateMetadata(
                    path=path,
                    created_at=stat.st_mtime,
                )
                self.states.append(metadata)
                LOGGER.debug("Found storage state: %s", path.name)
            except Exception as exc:
                LOGGER.warning("Failed to load storage state %s: %s", path, exc)
        
        # Sort by creation time (newest first)
        self.states.sort(key=lambda s: s.created_at, reverse=True)
        LOGGER.info("Loaded %d storage state(s)", len(self.states))
    
    def get_fresh_state(self) -> Optional[Path]:
        """Get a fresh storage state path.
        
        Returns
        -------
        Path or None
            Path to fresh storage state, or None if none available
        """
        for state in self.states:
            if state.is_valid and state.is_fresh(self.max_age_seconds):
                LOGGER.debug("Using storage state: %s", state.path.name)
                return state.path
        
        LOGGER.warning("No fresh storage state available")
        return None
    
    def add_state(
        self,
        state_data: Dict[str, Any],
        *,
        name: Optional[str] = None,
        source: str = "local",
    ) -> Path:
        """Add a new storage state.
        
        Parameters
        ----------
        state_data : dict
            Storage state data (cookies, localStorage, etc.)
        name : str, optional
            Custom name for the state file
        source : str
            Source of the state (local, s3, manual)
            
        Returns
        -------
        Path
            Path to the saved storage state
        """
        if name is None:
            timestamp = int(time.time())
            name = f"storage-state-{timestamp}.json"
        
        if not name.endswith(".json"):
            name = f"{name}.json"
        
        path = self.storage_dir / name
        
        # Save state
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)
        
        # Add metadata
        metadata = StorageStateMetadata(
            path=path,
            created_at=time.time(),
            source=source,
        )
        self.states.insert(0, metadata)  # Add to front (newest)
        
        LOGGER.info("Added new storage state: %s (source=%s)", name, source)
        return path
    
    def mark_invalid(self, path: Path) -> None:
        """Mark a storage state as invalid.
        
        Parameters
        ----------
        path : Path
            Path to the storage state
        """
        for state in self.states:
            if state.path == path:
                state.is_valid = False
                state.verification_failures += 1
                LOGGER.warning(
                    "Marked storage state as invalid: %s (failures=%d)",
                    path.name,
                    state.verification_failures,
                )
                break
    
    def mark_verified(self, path: Path) -> None:
        """Mark a storage state as verified.
        
        Parameters
        ----------
        path : Path
            Path to the storage state
        """
        for state in self.states:
            if state.path == path:
                state.last_verified = time.time()
                state.is_valid = True
                LOGGER.debug("Verified storage state: %s", path.name)
                break
    
    def cleanup_old_states(self, keep_count: int = 5) -> int:
        """Remove old storage states, keeping only the newest N.
        
        Parameters
        ----------
        keep_count : int
            Number of states to keep (default: 5)
            
        Returns
        -------
        int
            Number of states removed
        """
        removed = 0
        
        # Sort by creation time
        sorted_states = sorted(self.states, key=lambda s: s.created_at, reverse=True)
        
        for state in sorted_states[keep_count:]:
            try:
                state.path.unlink()
                self.states.remove(state)
                removed += 1
                LOGGER.debug("Removed old storage state: %s", state.path.name)
            except Exception as exc:
                LOGGER.warning("Failed to remove %s: %s", state.path, exc)
        
        if removed > 0:
            LOGGER.info("Cleaned up %d old storage state(s)", removed)
        
        return removed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about storage states.
        
        Returns
        -------
        dict
            Statistics dictionary
        """
        valid_states = [s for s in self.states if s.is_valid]
        fresh_states = [s for s in valid_states if s.is_fresh(self.max_age_seconds)]
        
        return {
            "total_states": len(self.states),
            "valid_states": len(valid_states),
            "fresh_states": len(fresh_states),
            "oldest_state_age_hours": (
                (time.time() - min(s.created_at for s in self.states)) / 3600
                if self.states else 0
            ),
            "newest_state_age_hours": (
                (time.time() - max(s.created_at for s in self.states)) / 3600
                if self.states else 0
            ),
        }

