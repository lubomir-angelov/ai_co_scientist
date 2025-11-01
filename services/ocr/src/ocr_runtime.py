# services/ocr/src/ocr_runtime.py
class DeepSeekOCRPipeline:
    def __init__(self):
        # load / init your deepseek components here
        ...

    def process_bytes(self, data: bytes, doc_id: str):
        # 1) run deepseek-ocr on bytes
        # 2) parse into sections/tables/metadata
        # return a dict like below
        return {
            "sections": [{"name": "FullText", "text": "..." }],
            "tables": [],
            "metadata": {"doc_id": doc_id},
        }

def load_deepseek_ocr() -> DeepSeekOCRPipeline:
    return DeepSeekOCRPipeline()
