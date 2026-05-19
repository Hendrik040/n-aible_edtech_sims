"""
AI Gateway placeholder for backend_v2.

The previous implementation re-exported LangChain-backed helpers from
`common/services/simulation_helper/`. Those helpers have been removed as part
of the Agent SDK rewrite. This module is retained as an empty placeholder so
that import references in the package tree remain resolvable; the gateway
surface will be rebuilt on top of the Claude Agent SDK in a later ticket.
"""

__all__: list[str] = []
