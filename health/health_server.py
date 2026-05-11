"""
Health Check Server for Railway Deployment.

Provides a minimal HTTP endpoint that responds with system health status.
Only starts when the PORT environment variable is set (Railway sets this
automatically for web services).

Requirements: 9.5, 9.9
"""

import logging
import os
import time
from typing import Optional

from aiohttp import web

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """
    Minimal HTTP server for Railway health checks.

    Responds to any request with HTTP 200 and a JSON body containing:
    - status: "healthy"
    - uptime_seconds: seconds since server started
    - monitored_symbols: count of symbols being monitored
    - active_positions: count of active trailing stop positions

    The server only starts when the PORT environment variable is set.
    Responses are guaranteed within 1 second.

    Requirements:
        9.5 - Health check endpoint on PORT with HTTP 200 + JSON
        9.9 - Response within 1 second
    """

    def __init__(self, scanner) -> None:
        """
        Initialize the HealthCheckServer.

        Args:
            scanner: The MomentumScanner instance to query for status.
        """
        self._scanner = scanner
        self._start_time: float = time.time()
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._port: Optional[int] = None

    @property
    def port(self) -> Optional[int]:
        """The port the server is listening on, or None if not started."""
        return self._port

    async def start(self) -> None:
        """
        Start the HTTP health check server if PORT env var is set.

        If PORT is not set, this method is a no-op (local development).
        """
        port_str = os.environ.get("PORT")
        if not port_str:
            logger.debug("PORT env var not set, health check server disabled")
            return

        try:
            self._port = int(port_str)
        except ValueError:
            logger.error("Invalid PORT value: %s", port_str)
            return

        self._start_time = time.time()
        self._app = web.Application()
        self._app.router.add_route("*", "/{path_info:.*}", self._handle_request)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "0.0.0.0", self._port)
        await self._site.start()

        logger.info("Health check server started on port %d", self._port)

    async def stop(self) -> None:
        """Stop the HTTP health check server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
            self._app = None
            logger.info("Health check server stopped")

    async def _handle_request(self, request: web.Request) -> web.Response:
        """
        Handle any incoming HTTP request with a health status response.

        Returns HTTP 200 with JSON body containing uptime and status.
        Guaranteed to respond within 1 second.

        Args:
            request: The incoming aiohttp request.

        Returns:
            JSON response with health status.
        """
        uptime_seconds = round(time.time() - self._start_time, 2)

        # Get monitored symbols count
        monitored_symbols = len(self._scanner._symbols) if self._scanner else 0

        # Get active positions count from trailing stop monitor
        active_positions = 0
        if self._scanner and hasattr(self._scanner, "_trailing_stop_monitor"):
            try:
                positions = self._scanner._trailing_stop_monitor.get_monitored_positions()
                active_positions = len(positions)
            except Exception:
                pass

        body = {
            "status": "healthy",
            "uptime_seconds": uptime_seconds,
            "monitored_symbols": monitored_symbols,
            "active_positions": active_positions,
        }

        return web.json_response(body, status=200)
