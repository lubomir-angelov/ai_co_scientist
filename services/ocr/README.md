# deep_seek_ocr
A DeepSek OCR server as a tool to OctoTools.

Running within a docker container to support a cuda:12.8.1 image and no vllm_cu118 as it's not yet compatible with more recent cuda.

# export local env vars
```bash
export BASE_IMAGE="nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04"
export IMAGE_TAG="deepseek-ocr-service"
```

# build
```bash
docker build \
  --build-arg BASE_IMAGE="${BASE_IMAGE}" \
  -t "${IMAGE_TAG}" .
```

# run
```bash
docker run -it --rm --gpus all \
  -p 8000:8000 \
  -v $PWD/shared:/workspace/shared \
  "${IMAGE_TAG}"
```