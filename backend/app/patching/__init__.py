"""Patch construction, diffing and safe application."""

from app.patching.differ import apply_proposal, make_unified_diff
from app.patching.templates import template_patch

__all__ = ["apply_proposal", "make_unified_diff", "template_patch"]
