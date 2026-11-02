"""
Runtime Event Bus Module

Implements a local publish-subscribe event system for communication between perception, planner, and executor.
"""

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = {}

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> None:
        """Subscribes a callback function to an event type."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.debug("Subscribed callback to event type: %s", event_type)

    def publish(self, event_type: str, data: Any) -> None:
        """Publishes an event with associated payload data to all subscribers."""
        if event_type not in self._subscribers:
            return

        logger.debug("Publishing event '%s' to %d subscribers", event_type, len(self._subscribers[event_type]))
        for callback in self._subscribers[event_type]:
            try:
                callback(data)
            except Exception as exc:
                logger.error("Error running event callback for %s: %s", event_type, exc)
                # Do not let callback failures crash the event dispatch loop
                pass
                
    def clear(self) -> None:
        """Clears all subscribers."""
        self._subscribers.clear()
        logger.debug("Cleared event bus subscribers")
