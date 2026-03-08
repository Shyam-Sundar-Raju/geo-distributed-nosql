# Geo-Distributed NoSQL + Product Store Prototype

A FastAPI-based distributed key-value and product inventory system with quorum replication, periodic anti-entropy sync, and a per-node web UI.

## What This Project Implements

- Geo-style multi-node deployment using Docker containers.
- Quorum-style reads and writes where:
  - `N = total nodes known by a node (self + peers)`
  - `W = majority = floor(N/2) + 1`
  - `R = majority = floor(N/2) + 1`
- Last-write-wins conflict handling using timestamps.
- Startup sync + periodic full-state synchronization every 30 seconds.
- Product operations with replicated storage:
  - Create product
  - Update product info
  - Add stock
  - Purchase (stock decreases)
  - Delete product (tombstone-based)
- Node-local web page for product management.

## Project Structure

```text
geo-distributed-nosql/
├── app/
│   ├── server.py              # API server and replication logic
│   ├── requirements.txt
│   └── static/
│       └── index.html         # Web UI per node
├── Dockerfile
├── docker-compose.yml         # 3-node local setup + toxiproxy
├── setup-proxies.sh           # Latency injection for local simulation
├── run.sh                     # Local compose up + proxy setup
├── start-cluster.sh           # 3-machine role-based startup
├── stop-cluster.sh            # 3-machine role-based stop
├── terminate.sh               # wrapper for stop-cluster.sh
├── read-quorum-test.sh
└── write-quorum-test.sh
```

## Architecture

Each node runs the same service and can act as coordinator for client requests.

State model stored in `store.json`:

```json
{
  "kv": {
    "someKey": { "value": "...", "timestamp": 1234567890.12 }
  },
  "products": {
    "p1": {
      "product_id": "p1",
      "name": "Tea",
      "description": "...",
      "price": 10.0,
      "stock": 5,
      "timestamp": 1234567890.12,
      "deleted": false
    }
  }
}
```

## Replication and Consistency Model

1. Client writes to any node.
2. Coordinator writes locally.
3. Coordinator forwards to all peers through internal replication endpoints.
4. Request succeeds only if acknowledgements `>= W`.
5. Reads query local + peers and require responses `>= R`.
6. Latest timestamp wins when multiple versions are seen.
7. Background sync (`/internal/fullstate`) helps eventual convergence.

Notes:
- This is quorum/eventual consistency, not consensus (no Raft/Paxos).
- Product deletion is tombstone-based (`deleted: true`) to replicate deletes safely.

## API Reference

### Public Endpoints

- `GET /` -> Serves node web UI (`app/static/index.html`)
- `GET /health` -> Node health + peer list
- `GET /keys` -> Full key-value map
- `POST /put` -> Quorum write for key-value
- `GET /get/{key}` -> Quorum read for key-value

### Product Endpoints

- `GET /products`
  - Returns active (non-deleted) products.
- `POST /products`
  - Creates a product.
  - Body:
    ```json
    {
      "product_id": "p1",
      "name": "Tea",
      "description": "250g",
      "price": 10.5,
      "stock": 5
    }
    ```
- `PUT /products/{product_id}`
  - Updates name/description/price.
- `POST /products/{product_id}/stock`
  - Adds stock.
  - Body: `{ "amount": 10 }`
- `POST /products/{product_id}/purchase`
  - Purchases quantity and reduces stock.
  - Body: `{ "quantity": 2 }`
- `DELETE /products/{product_id}`
  - Soft delete using tombstone replication.

### Internal Endpoints (Node-to-Node)

- `POST /internal/replicate`
- `GET /internal/get/{key}`
- `POST /internal/replicate_product`
- `GET /internal/fullstate`

## Web UI Features

Open any node URL and use the form-based interface:

- Create Product
- Update Product Info
- Add Stock
- Purchase Product (stock decreases)
- Delete Product
- Live product table and status feedback

Local URLs (default):
- `http://localhost:5001`
- `http://localhost:5002`
- `http://localhost:5003`

## Run Locally (Single Machine, 3 Nodes)

Prerequisites:
- Docker Engine
- Docker Compose v2 (`docker compose`)
- `jq` (for `setup-proxies.sh`)

Commands:

```bash
cd /home/shyam/Desktop/Projects/dist_sys/geo-distributed-nosql
./run.sh
```

`run.sh` performs:

```bash
docker compose down
docker compose up -d --build
./setup-proxies.sh
```

Manual alternative:

```bash
docker compose up -d --build
./setup-proxies.sh
```

Stop:

```bash
docker compose down
```

## Run Across 3 Machines (9 Nodes Total)

This repo includes role-based scripts for the layout:

- `machine1`: `mumbai`, `chennai`, `bangalore`
- `machine2`: `virginia`, `newyork`, `wasdc`
- `machine3`: `set3a`, `set3b`, `set3c`

Run on each machine:

```bash
./start-cluster.sh <machine1|machine2|machine3> <M1_IP> <M2_IP> <M3_IP>
```

Example:

```bash
./start-cluster.sh machine1 10.0.0.11 10.0.0.12 10.0.0.13
```

Stop:

```bash
./stop-cluster.sh machine1
./stop-cluster.sh machine2
./stop-cluster.sh machine3
# or
./stop-cluster.sh all
```

Wrapper:

```bash
./terminate.sh machine1
```

Network requirements:
- Allow TCP ports `5001`, `5002`, `5003` between all machines.

## Quick Verification

Health:

```bash
curl http://localhost:5001/health
```

Create a product on one node:

```bash
curl -X POST http://localhost:5001/products \
  -H "Content-Type: application/json" \
  -d '{"product_id":"p1","name":"Tea","description":"test","price":10,"stock":5}'
```

Read from another node:

```bash
curl http://localhost:5002/products
```

Purchase and reduce stock:

```bash
curl -X POST http://localhost:5003/products/p1/purchase \
  -H "Content-Type: application/json" \
  -d '{"quantity":2}'
```

## Troubleshooting

### 1) `docker-compose` fails with `http+docker`
Use Compose v2 plugin:

```bash
docker compose up -d --build
```

Do not use legacy `docker-compose` on this setup.

### 2) `setup-proxies.sh` fails
Install `jq`:

```bash
sudo apt-get update && sudo apt-get install -y jq
```

### 3) Nodes not syncing across machines
- Verify firewall/security group allows 5001-5003 inbound.
- Verify reachable IPs with `curl http://<peer-ip>:5001/health`.
- Ensure each node's `PEERS` contains all other nodes (not itself).

## Current Limitations

- No Raft/Paxos or distributed transactions.
- Last-write-wins may overwrite concurrent updates.
- No authentication/TLS between nodes.
- No region-aware routing policy beyond static peers.

## License / Purpose

Educational prototype for quorum replication, multi-node fault tolerance, and geo-distributed behavior simulation.
