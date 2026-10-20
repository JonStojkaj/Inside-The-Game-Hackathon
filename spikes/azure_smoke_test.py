"""Check that we can reach the Foundry deployment with keyless auth (az login).

Run from repo root:  backend/.venv/bin/python spikes/azure_smoke_test.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
deployment = os.environ["AZURE_OPENAI_DEPLOYMENT_FAST"]
token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")
client = OpenAI(base_url=endpoint, api_key=token_provider)

started = time.perf_counter()
response = client.chat.completions.create(
    model=deployment,
    messages=[{"role": "user", "content": "Reply with exactly: Sliding Doors online"}],
)
elapsed = time.perf_counter() - started

print(f"deployment : {deployment}")
print(f"model      : {response.model}")
print(f"reply      : {response.choices[0].message.content}")
print(f"latency    : {elapsed:.2f} s")
print(f"tokens     : {response.usage.total_tokens if response.usage else 'n/a'}")
