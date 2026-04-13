"""
Simulation Router Wiring (stub for backend_v2 scaffold).

The simulation module has been removed from backend_v2 and will be
reimplemented on top of the Claude Agent SDK in later tickets. For now this
wiring file exposes an empty APIRouter so that `app.main` can still include it.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])
