# Services

Each directory is an independently buildable microservice with its own `Makefile`,
`compose.yaml` (except `common`) and tests. The root `docker-compose.yml` includes the compose
files. See `../DOCKER_COMPOSE.md`.

```
services/
├── llm/          # llama.cpp server (Qwen3.8 27B) + API-key gateway          :8000 / :9000
├── ocr/          # DeepSeek-OCR FastAPI service (GPU)                          :8002
├── ocr_mcp/      # MCP server exposing OCR as tools                            :8003
├── memory/       # Graphiti temporal knowledge graph (+ FalkorDB, embeddings) :8005
├── octo_agent/   # OctoTools-style planner/executor/solver + tool wrappers     :8001 (opt-in)
└── common/       # shared_library: cross-service contracts and interfaces
```

Every Python service's Makefile has the same core targets:

```bash
make -C services/<svc> help
make -C services/<svc> install   # per-service virtualenv (octo_agent: ~/venvs/ai_cosc_orchestrator)
make -C services/<svc> test
make -C services/<svc> lint      # ruff
make -C services/<svc> up        # run this service standalone (docker compose)
```

# How-To's
## setup docker
Install Docker Desktop for your preferred env, we used Docker Desktop for windows with WSL2

## setup nvidia-container-toolkit

The container toolkit is backporting to older versions of Ubuntu in the keyring file and is using the $(ARCH) which will not be expanded by apt-get.

```bash
# You might see errors like: 
# Reading package lists... Done
# W: GPG error: https://nvidia.github.io/libnvidia-container/stable/deb/amd64  InRelease: The following signatures couldn't be verified because the public key is not available: NO_PUBKEY DDCAE044F796ECB0
# E: The repository 'https://nvidia.github.io/libnvidia-container/stable/deb/amd64  InRelease' is not signed.
# N: Updating from such a repository can't be done securely, and is therefore disabled by default.
# N: See apt-secure(8) manpage for repository creation and user configuration details.
# W: GPG error: https://nvidia.github.io/libnvidia-container/stable/ubuntu18.04/amd64  InRelease: The following signatures couldn't be verified because the public key is not available: NO_PUBKEY DDCAE044F796ECB0
# E: The repository 'https://nvidia.github.io/libnvidia-container/stable/ubuntu18.04/amd64  InRelease' is not signed.
# N: Updating from such a repository can't be done securely, and is therefore disabled by default.
# N: See apt-secure(8) manpage for repository creation and user configuration details.
# OR
# E: The repository 'https://nvidia.github.io/libnvidia-container/stable/ubuntu18.04/amd64  InRelease' is not signed.
# The proper way is to hardcode the 18.04 and your current arch (e.g. amd64).
# first make the folder
sudo mkdir -p /usr/share/keyrings

# get the gpg key
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

# hardcode the os version and your architecture (we are using amd64)
sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null << 'EOF'
deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/ubuntu22.04/amd64 /
EOF

# update and install 
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# setup the nvidia runtime to point to docker
sudo nvidia-ctk runtime configure --runtime=docker

# restart docker 
sudo service docker restart || true

# OR via the Docker Destkop restart option

# check the container can see the local cuda
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```


## Git empty objects
```bash
# 1) Remove the specific corrupt object Git reports

# Run in the failing repo (ai_co_scientist.clean):

cd ~/repos/ai_co_scientist.clean

rm -f .git/objects/38/63f9095bf20e86d80f63d655ea2b6433d566b6


# Then:

git fetch --all --prune


# If it succeeds, finish with:

git fsck --full
git gc --prune=now
```