"""
MRL_router.py — Channel router for MRL particle flows

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

Routes incoming particle packets to registered channel handlers.
Supports: unicast, broadcast, multicast, and frequency-based jump routing.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Handler = Callable[[str, dict], Any]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

class MRLRouter:
    """
    Simple in-process channel router.

    Usage::

        router = MRLRouter()

        @router.on("system")
        def handle_system(channel: str, packet: dict) -> None:
            print(f"system channel got: {packet}")

        router.route("system", {"fl": "fl-001", "payload": "hello"})
        router.broadcast({"fl": "fl-002", "payload": "all"})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._catch_all: list[Handler] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on(self, channel: str) -> Callable:
        """Decorator: register a handler for a named channel."""
        def decorator(fn: Handler) -> Handler:
            self._handlers[channel].append(fn)
            logger.debug("Registered handler %s on channel '%s'", fn.__name__, channel)
            return fn
        return decorator

    def register(self, channel: str, handler: Handler) -> None:
        """Register a handler imperatively."""
        self._handlers[channel].append(handler)

    def register_catch_all(self, handler: Handler) -> None:
        """Register a handler that receives every packet on every channel."""
        self._catch_all.append(handler)

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------

    def route(self, channel: str, packet: dict) -> list[Any]:
        """
        Route a packet to all handlers registered on *channel*.

        Returns list of handler results.
        """
        results: list[Any] = []
        handlers = self._handlers.get(channel, []) + self._catch_all
        if not handlers:
            logger.warning("No handler for channel '%s'; packet dropped.", channel)
            return results
        for h in handlers:
            try:
                results.append(h(channel, packet))
            except Exception as exc:  # noqa: BLE001
                logger.error("Handler %s on channel '%s' raised: %s", h.__name__, channel, exc)
        return results

    def broadcast(self, packet: dict) -> dict[str, list[Any]]:
        """
        Send packet to ALL registered channels.

        Returns dict mapping channel → list of results.
        """
        all_results: dict[str, list[Any]] = {}
        for channel in list(self._handlers.keys()):
            all_results[channel] = self.route(channel, packet)
        return all_results

    def multicast(self, channels: list[str], packet: dict) -> dict[str, list[Any]]:
        """
        Send packet to a specified subset of channels.

        Returns dict mapping channel → list of results.
        """
        return {ch: self.route(ch, packet) for ch in channels}

    def jump(self, from_channel: str, to_channel: str, packet: dict) -> list[Any]:
        """
        Jump-route: switch packet from one channel to another.

        Analogous to the 'jump' command in MRL Shell (fl-100).
        """
        logger.info("JUMP %s → %s", from_channel, to_channel)
        packet = {**packet, "_jumped_from": from_channel}
        return self.route(to_channel, packet)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def channels(self) -> list[str]:
        """List all registered channel names."""
        return list(self._handlers.keys())

    def handler_count(self, channel: str) -> int:
        """Return number of handlers on a channel."""
        return len(self._handlers.get(channel, []))

    def status(self) -> dict:
        """Return a status summary dict."""
        return {
            "channels": self.channels(),
            "catch_all_count": len(self._catch_all),
            "handler_counts": {ch: len(hs) for ch, hs in self._handlers.items()},
        }


# ---------------------------------------------------------------------------
# Module-level default router
# ---------------------------------------------------------------------------

_default_router = MRLRouter()


def get_router() -> MRLRouter:
    """Return the module-level default router."""
    return _default_router


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import argparse

    parser = argparse.ArgumentParser(description="MRL Router — inspect routing table")
    parser.add_argument("--status", action="store_true", help="Print router status")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(_default_router.status(), indent=2))
    else:
        parser.print_help()
