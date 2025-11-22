import os
from openai import OpenAI

base_url = os.getenv("LLM_BASE_URL", "http://localhost:9000/v1")
api_key  = os.getenv("LLM_API_KEY", "local-llm")
model    = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B")

client = OpenAI(base_url=base_url, api_key=api_key)

resp = client.chat.completions.create(
    model=model,
    temperature=0.6,
    messages=[{"role":"user","content":"<think>\nGive me a 3-step plan to debug a flaky integration test."}]
)
print(resp.choices[0].message.content)
