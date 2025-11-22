# Usage
cd services/orchestrator

# Setup venv and install dependencies
make venv
make install
make install-test

# Show PYTHONPATH
make pythonpath

# Run tests with PYTHONPATH set
make test
make test-registry

# Run Python with PYTHONPATH
make python SCRIPT=scripts/test_tools.py

# Activate venv
source ~/venvs/ai_cosc_orchestrator/bin/activate