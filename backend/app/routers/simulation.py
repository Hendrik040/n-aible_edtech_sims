"""
Simulation Router Wiring.

Thin wiring layer that imports and includes the simulation module router.
"""

from modules.simulation.router import router  # noqa: F401

# Router is already configured with prefix="/api/simulation"
# Just export it for inclusion in main.py

