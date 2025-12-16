"""
Models and data structures - imported from vendor/octotools
"""

import sys
from pathlib import Path

# Add vendor to path
repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
vendor_path = repo_root / "vendor" / "octotools"
if str(vendor_path) not in sys.path:
    sys.path.insert(0, str(vendor_path))

# Import everything from vendor/octotools
from octotools.models.formatters import (
    QueryAnalysis,
    NextStep,
    ToolCommand,
    MemoryVerification
)
from octotools.models.memory import Memory
from octotools.models.planner import Planner
from octotools.models.executor import Executor
from octotools.models.initializer import Initializer

__all__ = [
    'QueryAnalysis', 'NextStep', 'ToolCommand', 'MemoryVerification',
    'Memory', 'Planner', 'Executor', 'Initializer'
]
