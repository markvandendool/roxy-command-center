"""
ROXY Command Center Services

Thin-client services adapted to current ROXY.
Current review build uses local Ollama directly and keeps system controls read-only.
"""

# Keep package import lightweight. Optional UI stacks such as chat can require
# additional GI namespaces that are not needed for status/profile smoke tests.
__all__ = []
