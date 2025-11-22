"""
LLM Engines - minimal adapter layer
Imports from vendor/octotools, adapts for services
"""

import sys
from pathlib import Path

# Add vendor to path for imports
repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
vendor_path = repo_root / "vendor" / "octotools"
if str(vendor_path) not in sys.path:
    sys.path.insert(0, str(vendor_path))

# Import base classes from vendor
from octotools.engine.base import EngineLM, CachedEngine

# Import local implementation
from .local_llm import ChatLocalLLM

__all__ = ['EngineLM', 'CachedEngine', 'ChatLocalLLM']
