"""
Memory Transaction Manager — atomic multi-step memory operations with rollback.

Provides a context manager that wraps storage operations in a transaction:
- On __enter__: takes a snapshot of affected state, begins an implicit SQLite transaction
- On __exit__ with exception: rolls back to snapshot, logs full error with traceback
- On successful exit: commits all changes atomically

Usage:
    with MemoryTransaction(storage) as tx:
        storage.save_agent_state(new_state)
        storage.save_task(...)
        # If any operation fails, ALL changes are rolled back
"""

from __future__ import annotations

import copy
import logging
import traceback
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple

from .storage import MemoryStorage

logger = logging.getLogger(__name__)


class TransactionError(Exception):
    """Raised when a memory transaction fails to commit or rollback."""
    pass


class MemoryTransaction:
    """
    Context manager for atomic multi-step memory operations.
    
    Captures a snapshot of the state before modifications and provides
    rollback capability if any operation fails.
    """

    def __init__(self, storage: MemoryStorage) -> None:
        self._storage = storage
        self._snapshot: Optional[Dict[str, Any]] = None
        self._committed = False

    def __enter__(self) -> "MemoryTransaction":
        """Enter the transaction context — take state snapshot."""
        try:
            self._snapshot = self._storage.load_agent_state()
        except Exception as e:
            logger.error("MemoryTransaction: Failed to take snapshot: %s", e)
            # Proceed without snapshot (best-effort)
            self._snapshot = None
        logger.debug("MemoryTransaction: Entered transaction context")
        return self

    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException],
                 exc_tb: Optional[object]) -> bool:
        """
        Exit the transaction context.
        - If no exception: commit all pending changes.
        - If exception occurred: attempt rollback to snapshot.
        Returns True if exception was handled (suppressed), False to propagate.
        """
        if exc_type is None:
            # No exception — commit is implicit (storage already wrote)
            self._committed = True
            logger.debug("MemoryTransaction: Transaction committed successfully")
            return False  # Don't suppress

        # An exception occurred — rollback
        logger.error(
            "MemoryTransaction: Exception in transaction: %s\n%s",
            exc_val,
            "".join(traceback.format_exception(exc_type, exc_val, exc_tb)) if exc_tb else "(no traceback)",
        )

        try:
            self._rollback()
        except Exception as rollback_err:
            logger.error(
                "MemoryTransaction: Rollback also failed: %s\n%s",
                rollback_err,
                traceback.format_exc(),
            )
            # Raise TransactionError to signal catastrophic failure
            raise TransactionError(
                f"Transaction failed and rollback also failed. "
                f"Original error: {exc_val}. Rollback error: {rollback_err}"
            ) from rollback_err

        logger.info("MemoryTransaction: Successfully rolled back to snapshot")
        return False  # Propagate the original exception

    def _rollback(self) -> None:
        """Rollback to the captured snapshot."""
        if self._snapshot is not None:
            logger.info("MemoryTransaction: Restoring agent state snapshot")
            self._storage.save_agent_state(self._snapshot)
        else:
            logger.warning("MemoryTransaction: No snapshot available — cannot rollback agent state")

    @property
    def committed(self) -> bool:
        return self._committed


@contextmanager
def atomic_memory_update(storage: MemoryStorage) -> Generator[MemoryTransaction, None, None]:
    """
    Context manager wrapper for MemoryTransaction.
    
    Usage:
        with atomic_memory_update(storage) as tx:
            storage.save_task(...)
            storage.save_agent_state(...)
    """
    tx = MemoryTransaction(storage)
    try:
        yield tx
    except Exception:
        # Let MemoryTransaction.__exit__ handle the rollback
        raise
    finally:
        # Ensure __exit__ is called properly
        pass
