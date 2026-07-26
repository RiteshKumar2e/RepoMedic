"""Patch construction, diffing and safe application."""

from app.patching.differ import apply_proposal, make_unified_diff  # noqa: F401
from app.patching.templates import template_patch  # noqa: F401

__all__ = ["apply_proposal", "make_unified_diff", "template_patch"]
