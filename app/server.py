import os
import time
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict

app = FastAPI()

# Configuration
NODE_NAME = os.getenv("NODE_NAME", "node")
PEERS = os.getenv("PEERS", "").split(",") if os.getenv("PEERS") else []
N = 3
W = 2
R = 2

# In-memory store
store: Dict[str, Dict] = {}

class Item(BaseModel):
    key: str
    value: str


@app.get("/health")
def health():
    return {"node": NODE_NAME, "status": "healthy"}


@app.post("/internal/replicate")
def internal_replicate(item: Item):
    timestamp = time.time()
    store[item.key] = {"value": item.value, "timestamp": timestamp}
    return {"status": "replicated", "node": NODE_NAME}


@app.post("/put")
def put(item: Item):
    timestamp = time.time()
    store[item.key] = {"value": item.value, "timestamp": timestamp}

    acks = 1  # self ACK

    for peer in PEERS:
        try:
            response = requests.post(
                f"http://{peer}/internal/replicate",
                json={"key": item.key, "value": item.value},
                timeout=2
            )
            if response.status_code == 200:
                acks += 1
        except:
            pass

    if acks >= W:
        return {"status": "write_success", "acks": acks}
    else:
        raise HTTPException(status_code=500, detail="Write quorum not met")


@app.get("/get/{key}")
def get(key: str):
    responses = []

    # include self
    if key in store:
        responses.append(store[key])

    for peer in PEERS:
        try:
            response = requests.get(f"http://{peer}/internal/get/{key}", timeout=2)
            if response.status_code == 200:
                responses.append(response.json())
        except:
            pass

    if len(responses) < R:
        raise HTTPException(status_code=500, detail="Read quorum not met")

    latest = max(responses, key=lambda x: x["timestamp"])
    return {"key": key, "value": latest["value"]}


@app.get("/internal/get/{key}")
def internal_get(key: str):
    if key not in store:
        raise HTTPException(status_code=404, detail="Key not found")
    return store[key]