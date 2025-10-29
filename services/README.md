# Services

We employ several microservices that constitue the ai_co_scientist.

Those are:

```
ai_co_scientist/
├── docker-compose.yml
├── services/
│   ├── orchestrator/ # This is where we wrap OctoTools itself. This service is the “brain that calls tools.” 
                      # It should not try to be the tools.
│   │   │
│   │   ├── src/
│   │   │   ├── agent_loop.py
│   │   │   ├── tools_registry.py
│   │   │   ├── adapters/        # http wrappers for OCR, memory, etc.
│   │   │   └── runtime_config.py
│   │   ├── Dockerfile
│   │   └── tests/
│   │   │ # The rest are all called by the orchestrator. Each exposes a tiny, well-defined HTTP API.
│   ├── memory/
│   ├── llm/
│   └── ocr/
│   ├── common/ # Is crucial. We don’t duplicate schemas, timestamps, provenance logic or logging config in four places. 
                # We make a light shared lib we can import from each service.
│   │   
└── vendor/
    └── octotools/   <-- git submodule of the original repo
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
