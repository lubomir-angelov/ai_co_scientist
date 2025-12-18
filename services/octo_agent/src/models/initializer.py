import os
import sys
import importlib
import inspect
import traceback
from typing import Dict, Any, List, Tuple
import time

import os
import sys
import importlib
import inspect
import traceback
from typing import Dict, Any, List, Optional


class Initializer:
    def __init__(
        self,
        enabled_tools: Optional[List[str]] = None,
        model_string: Optional[str] = None,
        verbose: bool = False,
        vllm_config_path: Optional[str] = None,
    ):
        self.toolbox_metadata: Dict[str, Any] = {}
        self.tool_classes: Dict[str, type] = {}  # class_name -> class
        self.tool_directory_mapping: Dict[str, str] = {}  # class_name -> directory
        self.available_tools: List[str] = []

        self.enabled_tools = enabled_tools or []
        self.load_all = self.enabled_tools == ["all"]
        self.model_string = model_string or ""
        self.verbose = verbose
        self.vllm_config_path = vllm_config_path

        print("\n==> Initializing octo_agent...")
        print(f"Enabled tools: {self.enabled_tools}")
        print(f"LLM engine name: {self.model_string}")

        self._set_up_tools()

        if self.model_string.startswith("vllm-"):
            self.setup_vllm_server()

    def get_project_root(self) -> str:
        # Assumes this file lives at services/octo_agent/src/models/initializer.py
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def load_tools_and_get_metadata(self) -> Dict[str, Any]:
        print("Loading tools and getting metadata...")
        self.toolbox_metadata = {}
        self.tool_classes = {}
        self.tool_directory_mapping = {}

        octo_agent_dir = self.get_project_root()  # .../services/octo_agent
        src_dir = os.path.join(octo_agent_dir, "src")
        tools_dir = os.path.join(src_dir, "tools")

        # IMPORTANT: since you run with PYTHONPATH="$(pwd)/src", treat src as import root.
        # Ensure src_dir is on sys.path (idempotent).
        if src_dir not in sys.path:
            sys.path.insert(0, src_dir)

        if self.verbose:
            print(f"octo_agent_dir: {octo_agent_dir}")
            print(f"src_dir: {src_dir}")
            print(f"tools_dir: {tools_dir}")
            print(f"sys.path[0:5]: {sys.path[0:5]}")

        if not os.path.isdir(tools_dir):
            print(f"Error: Tools directory does not exist: {tools_dir}")
            return self.toolbox_metadata

        # enabled directory names if user passed class names like Document_Parser_OCR_Tool
        enabled_dirnames = set(t.lower().replace("_tool", "") for t in self.enabled_tools)

        for root, _, files in os.walk(tools_dir):
            if "tool.py" not in files:
                continue

            tool_dirname = os.path.basename(root)  # e.g. document_parser_ocr

            # directory-level filter (only applies if not load_all)
            if (not self.load_all) and (tool_dirname not in enabled_dirnames):
                # NOTE: we still allow enabling by class name later; this is a fast skip.
                # If you want “class name enable only”, remove this continue and filter later.
                continue

            import_path = f"tools.{tool_dirname}.tool"
            print(f"\n==> Attempting to import: {import_path}")

            try:
                module = importlib.import_module(import_path)
            except Exception as e:
                print(f"Error importing {import_path}: {e}")
                if self.verbose:
                    print(traceback.format_exc())
                continue

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if not name.endswith("Tool") or name == "BaseTool":
                    continue

                # Ensure class is defined in this module (avoid imported classes)
                if obj.__module__ != module.__name__:
                    continue

                try:
                    if getattr(obj, "require_llm_engine", False):
                        tool_instance = obj(model_string=self.model_string)
                    else:
                        tool_instance = obj()
                except Exception as e:
                    print(f"Error instantiating {name}: {e}")
                    if self.verbose:
                        print(traceback.format_exc())
                    continue

                self.tool_classes[name] = obj
                self.tool_directory_mapping[name] = tool_dirname
                self.toolbox_metadata[name] = {
                    "tool_name": getattr(tool_instance, "tool_name", "Unknown"),
                    "tool_description": getattr(tool_instance, "tool_description", "No description"),
                    "tool_version": getattr(tool_instance, "tool_version", "Unknown"),
                    "input_types": getattr(tool_instance, "input_types", {}),
                    "output_type": getattr(tool_instance, "output_type", "Unknown"),
                    "demo_commands": getattr(tool_instance, "demo_commands", []),
                    "user_metadata": getattr(tool_instance, "user_metadata", {}),
                    "require_llm_engine": getattr(obj, "require_llm_engine", False),
                }

                print(f"Found tool class: {name}")

        print(f"\n==> Total number of tools imported: {len(self.toolbox_metadata)}")

        return self.toolbox_metadata
    
    def _set_up_tools(self) -> None:
        print("\n==> Setting up tools...")
    
        self.load_tools_and_get_metadata()
    
        if not self.load_all and self.enabled_tools:
            enabled_set = set(self.enabled_tools)
            # Keep only tools whose CLASS NAME is enabled
            self.toolbox_metadata = {k: v for k, v in self.toolbox_metadata.items() if k in enabled_set}
            self.tool_classes = {k: v for k, v in self.tool_classes.items() if k in enabled_set}
    
        self.available_tools = list(self.toolbox_metadata.keys())
    
        print("✅ Finished setting up tools.")
        print(f"✅ Total number of final available tools: {len(self.available_tools)}")
        print(f"✅ Final available tools: {self.available_tools}")



if __name__ == "__main__":
    enabled_tools = ["Document_Parser_OCR_Tool"]
    initializer = Initializer(enabled_tools=enabled_tools)

    print("\nAvailable tools:")
    print(initializer.available_tools)

    print("\nToolbox metadata for available tools:")
    print(initializer.toolbox_metadata)
    