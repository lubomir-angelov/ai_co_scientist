"""
Orchestrator Service - Core implementation
Main agent loop and FastAPI endpoints
"""

import sys
from pathlib import Path

# Setup vendor path for octotools imports
repo_root = Path(__file__).resolve().parent.parent.parent.parent
vendor_path = repo_root / "vendor" / "octotools"
if str(vendor_path) not in sys.path:
    sys.path.insert(0, str(vendor_path))

# Now import from vendor
from octotools.models.planner import Planner
from octotools.models.executor import Executor
from octotools.models.memory import Memory
from octotools.models.initializer import Initializer

# Import our custom engine adapter
from .engines.local_llm import ChatLocalLLM

__all__ = ['Planner', 'Executor', 'Memory', 'Initializer', 'ChatLocalLLM']
