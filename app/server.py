import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

STORE_FILE = "store.json"
NODE_NAME = os.getenv("NODE_NAME", "node")
BASE_DIR = Path(__file__).resolve().parent
UI_FILE = BASE_DIR / "static" / "index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Geo Distributed NoSQL Node")

# Shared in-memory state persisted to disk.
state: Dict[str, Dict] = {"kv": {}, "products": {}}
state_lock = threading.Lock()

# Configuration
PEERS = os.getenv("PEERS", "").split(",") if os.getenv("PEERS") else []
N = len(PEERS) + 1  # peers + self
W = (N // 2) + 1
R = (N // 2) + 1


class Item(BaseModel):
    key: str
    value: str


class ProductCreate(BaseModel):
    product_id: str
    name: str
    description: str = ""
    price: float = Field(..., ge=0)
    stock: int = Field(0, ge=0)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)


class StockRequest(BaseModel):
    amount: int = Field(..., gt=0)


class PurchaseRequest(BaseModel):
    quantity: int = Field(1, gt=0)


def load_store() -> None:
    global state
    if not os.path.exists(STORE_FILE):
        logger.info(f"[{NODE_NAME}] store.json not found, starting with empty state")
        return

    try:
        with open(STORE_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        # Backward compatibility: older version stored only a plain kv dictionary.
        if isinstance(loaded, dict) and "kv" not in loaded and "products" not in loaded:
            state = {"kv": loaded, "products": {}}
        else:
            state = {
                "kv": loaded.get("kv", {}),
                "products": loaded.get("products", {}),
            }

        logger.info(
            f"[{NODE_NAME}] Loaded kv={len(state['kv'])}, products={len(state['products'])}"
        )
    except Exception as exc:
        logger.warning(f"[{NODE_NAME}] Failed to load store.json, starting empty: {exc}")
        state = {"kv": {}, "products": {}}


def persist_store() -> None:
    with state_lock:
        snapshot = {"kv": state["kv"], "products": state["products"]}
    with open(STORE_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)


def periodic_sync() -> None:
    while True:
        time.sleep(30)
        sync_from_peers()


def apply_product_payload(payload: Dict) -> None:
    product_id = payload["product_id"]
    with state_lock:
        local = state["products"].get(product_id)
        if local is None or payload["timestamp"] >= local.get("timestamp", 0):
            state["products"][product_id] = payload


def replicate_product(payload: Dict) -> int:
    acks = 1
    for peer in PEERS:
        try:
            response = requests.post(
                f"http://{peer}/internal/replicate_product",
                json=payload,
                timeout=5,
            )
            if response.status_code == 200:
                acks += 1
        except Exception:
            logger.warning(f"[{NODE_NAME}] Failed product replication to {peer}")
    return acks


@app.on_event("startup")
def startup() -> None:
    load_store()
    sync_from_peers()
    threading.Thread(target=periodic_sync, daemon=True).start()


@app.get("/")
def index():
    if not UI_FILE.exists():
        raise HTTPException(status_code=404, detail="UI file not found")
    return FileResponse(UI_FILE)


@app.get("/health")
def health():
    return {"node": NODE_NAME, "status": "healthy", "peers": PEERS}


@app.get("/keys")
def get_all_keys():
    with state_lock:
        return state["kv"]


@app.post("/internal/replicate")
def internal_replicate(item: Item):
    timestamp = time.time()
    with state_lock:
        state["kv"][item.key] = {"value": item.value, "timestamp": timestamp}
    persist_store()
    return {"status": "replicated", "node": NODE_NAME}


@app.post("/internal/replicate_product")
def internal_replicate_product(payload: Dict):
    required = {"product_id", "name", "description", "price", "stock", "timestamp", "deleted"}
    if not required.issubset(set(payload.keys())):
        raise HTTPException(status_code=400, detail="Invalid product payload")
    apply_product_payload(payload)
    persist_store()
    return {"status": "product_replicated", "node": NODE_NAME}


@app.get("/internal/fullstate")
def full_state():
    with state_lock:
        return {"kv": state["kv"], "products": state["products"]}


@app.get("/internal/get/{key}")
def internal_get(key: str):
    with state_lock:
        if key not in state["kv"]:
            raise HTTPException(status_code=404, detail="Key not found")
        return state["kv"][key]


def sync_from_peers() -> None:
    logger.info(f"[{NODE_NAME}] Starting peer synchronization")

    for peer in PEERS:
        try:
            response = requests.get(f"http://{peer}/internal/fullstate", timeout=5)
            if response.status_code != 200:
                continue
            peer_state = response.json()

            peer_kv = peer_state.get("kv", {})
            peer_products = peer_state.get("products", {})

            with state_lock:
                for key, value in peer_kv.items():
                    if key not in state["kv"] or value["timestamp"] > state["kv"][key]["timestamp"]:
                        state["kv"][key] = value

                for product_id, product in peer_products.items():
                    local = state["products"].get(product_id)
                    if local is None or product.get("timestamp", 0) > local.get("timestamp", 0):
                        state["products"][product_id] = product

            logger.info(f"[{NODE_NAME}] Synced data from {peer}")
        except Exception as exc:
            logger.warning(f"[{NODE_NAME}] Failed to sync from {peer}: {exc}")

    persist_store()


@app.post("/put")
def put(item: Item):
    start_time = time.time()
    logger.info(f"[{NODE_NAME}] WRITE requested for key={item.key}")

    timestamp = time.time()
    with state_lock:
        state["kv"][item.key] = {"value": item.value, "timestamp": timestamp}

    acks = 1
    peer_latencies = []

    for peer in PEERS:
        peer_start = time.time()
        try:
            response = requests.post(
                f"http://{peer}/internal/replicate",
                json={"key": item.key, "value": item.value},
                timeout=5,
            )

            latency = time.time() - peer_start
            peer_latencies.append((peer, latency))

            if response.status_code == 200:
                acks += 1
                logger.info(f"[{NODE_NAME}] ACK from {peer} in {latency:.3f}s")
        except Exception:
            latency = time.time() - peer_start
            logger.warning(f"[{NODE_NAME}] FAILED contacting {peer} after {latency:.3f}s")

    total_time = time.time() - start_time

    logger.info(f"[{NODE_NAME}] WRITE completed | acks={acks} | total_time={total_time:.3f}s")

    if acks >= W:
        persist_store()
        return {
            "status": "write_success",
            "acks": acks,
            "total_time_seconds": round(total_time, 3),
            "peer_latencies": peer_latencies,
        }
    raise HTTPException(status_code=500, detail="Write quorum not met")


@app.get("/get/{key}")
def get(key: str):
    start_time = time.time()
    logger.info(f"[{NODE_NAME}] READ requested for key={key}")

    responses = []

    with state_lock:
        local = state["kv"].get(key)
    if local:
        responses.append(local)

    for peer in PEERS:
        peer_start = time.time()
        try:
            response = requests.get(f"http://{peer}/internal/get/{key}", timeout=5)
            latency = time.time() - peer_start

            if response.status_code == 200:
                responses.append(response.json())
                logger.info(f"[{NODE_NAME}] READ from {peer} in {latency:.3f}s")
        except Exception:
            latency = time.time() - peer_start
            logger.warning(f"[{NODE_NAME}] FAILED reading from {peer} after {latency:.3f}s")

    if len(responses) < R:
        raise HTTPException(status_code=500, detail="Read quorum not met")

    latest = max(responses, key=lambda x: x["timestamp"])
    total_time = time.time() - start_time
    logger.info(f"[{NODE_NAME}] READ completed | total_time={total_time:.3f}s")

    return {
        "key": key,
        "value": latest["value"],
        "total_time_seconds": round(total_time, 3),
    }


@app.get("/products")
def list_products():
    with state_lock:
        products = [p for p in state["products"].values() if not p.get("deleted", False)]
    products.sort(key=lambda p: p["product_id"])
    return {"node": NODE_NAME, "products": products}


@app.post("/products")
def create_product(payload: ProductCreate):
    now = time.time()
    product = {
        "product_id": payload.product_id,
        "name": payload.name,
        "description": payload.description,
        "price": payload.price,
        "stock": payload.stock,
        "timestamp": now,
        "deleted": False,
    }

    with state_lock:
        existing = state["products"].get(payload.product_id)
        if existing and not existing.get("deleted", False):
            raise HTTPException(status_code=409, detail="Product already exists")
        state["products"][payload.product_id] = product

    acks = replicate_product(product)
    if acks < W:
        raise HTTPException(status_code=500, detail="Write quorum not met for product creation")

    persist_store()
    return {"status": "created", "acks": acks, "product": product}


@app.put("/products/{product_id}")
def update_product(product_id: str, payload: ProductUpdate):
    with state_lock:
        current = state["products"].get(product_id)
        if not current or current.get("deleted", False):
            raise HTTPException(status_code=404, detail="Product not found")

        if payload.name is not None:
            current["name"] = payload.name
        if payload.description is not None:
            current["description"] = payload.description
        if payload.price is not None:
            current["price"] = payload.price

        current["timestamp"] = time.time()
        current["deleted"] = False
        updated = dict(current)

    acks = replicate_product(updated)
    if acks < W:
        raise HTTPException(status_code=500, detail="Write quorum not met for product update")

    persist_store()
    return {"status": "updated", "acks": acks, "product": updated}


@app.post("/products/{product_id}/stock")
def add_stock(product_id: str, payload: StockRequest):
    with state_lock:
        current = state["products"].get(product_id)
        if not current or current.get("deleted", False):
            raise HTTPException(status_code=404, detail="Product not found")

        current["stock"] += payload.amount
        current["timestamp"] = time.time()
        current["deleted"] = False
        updated = dict(current)

    acks = replicate_product(updated)
    if acks < W:
        raise HTTPException(status_code=500, detail="Write quorum not met for stock update")

    persist_store()
    return {"status": "stock_added", "acks": acks, "product": updated}


@app.post("/products/{product_id}/purchase")
def purchase_product(product_id: str, payload: PurchaseRequest):
    with state_lock:
        current = state["products"].get(product_id)
        if not current or current.get("deleted", False):
            raise HTTPException(status_code=404, detail="Product not found")
        if current["stock"] < payload.quantity:
            raise HTTPException(status_code=400, detail="Insufficient stock")

        current["stock"] -= payload.quantity
        current["timestamp"] = time.time()
        current["deleted"] = False
        updated = dict(current)

    acks = replicate_product(updated)
    if acks < W:
        raise HTTPException(status_code=500, detail="Write quorum not met for purchase")

    persist_store()
    return {
        "status": "purchased",
        "acks": acks,
        "product": updated,
        "purchased_quantity": payload.quantity,
    }


@app.delete("/products/{product_id}")
def delete_product(product_id: str):
    with state_lock:
        current = state["products"].get(product_id)
        if not current or current.get("deleted", False):
            raise HTTPException(status_code=404, detail="Product not found")

        current["deleted"] = True
        current["timestamp"] = time.time()
        deleted_snapshot = dict(current)

    acks = replicate_product(deleted_snapshot)
    if acks < W:
        raise HTTPException(status_code=500, detail="Write quorum not met for product deletion")

    persist_store()
    return {"status": "deleted", "acks": acks, "product_id": product_id}