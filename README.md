# Geo-Distributed NoSQL Prototype

**Docker-Based Quorum Replication System**

## 1. Overview

This project implements a **geo-distributed NoSQL prototype** that simulates multi-region replication using Docker containers. The system demonstrates:

* Low-latency regional reads
* High availability during regional failures
* Fault tolerance via replica redundancy
* Quorum-based consistency guarantees

The architecture follows an **AP-preferred distributed model**, where availability and partition tolerance are prioritized, and consistency is tunable via quorum configuration.

---

## 2. Background Theory

### 2.1 The Core Problem

In geo-distributed systems:

* Data spread across regions increases latency.
* Network partitions can isolate regions.
* Regional outages must not take down the system.

To solve this, data is **replicated across multiple regions**.

---

### 2.2 Replication Strategies

From the presentation (Page 2):

#### 1. Synchronous Replication

* All replicas must acknowledge before responding.
* Guarantees strong consistency.
* Higher latency.

#### 2. Asynchronous Replication

* Primary acknowledges first.
* Replicas sync later.
* Faster writes.
* Eventual consistency.

#### 3. Semi-Synchronous

* Subset of replicas must ACK.
* Practical balance between latency and consistency.

**This prototype implements a quorum-based semi-synchronous strategy.**

---

### 2.3 Consistency Models

From Page 3:

* **Strong Consistency** – Always return latest value.
* **Eventual Consistency** – Replicas converge over time.
* **Causal Consistency**
* **Read-Your-Writes**

NoSQL systems typically prioritize:

> Availability + Partition Tolerance (AP in CAP theorem)

This prototype ensures:

* Eventual consistency
* Read-write overlap using quorum

---

### 2.4 Quorum Theory

A quorum is defined as:

> The minimum number of replicas that must agree for a read or write to succeed.

Configuration (Page 4):

* **N = 3** (total replicas)
* **W = 2** (write acknowledgements required)
* **R = 2** (read replicas queried)

Guarantee:

```
R + W > N
```

Since:

```
2 + 2 > 3
```

There is guaranteed overlap between read and write sets, ensuring consistency.

---

## 3. System Architecture

### 3.1 Replica Layout

Three Docker containers simulate regions:

| Region    | Port |
| --------- | ---- |
| Mumbai    | 5001 |
| Virginia  | 5002 |
| Frankfurt | 5003 |

Each container:

* Runs an independent replica
* Maintains its own key-value store
* Communicates via HTTP

Container isolation simulates data-center separation.

---

## 4. Prototype Design

### 4.1 Functional Requirements

Each replica must support:

* `PUT /key` – write key-value pair
* `GET /key` – retrieve value
* Health check endpoint
* Versioning for conflict resolution

---

### 4.2 Write Flow (Quorum-Based)

1. Client sends write to coordinator (any node).
2. Coordinator forwards write to all replicas.
3. Replicas store value with timestamp/version.
4. Coordinator waits for **W = 2 ACKs**.
5. Once 2 ACKs received → success returned.

If only 1 ACK:

* Retry or return failure depending on design.

---

### 4.3 Read Flow

1. Client sends read to coordinator.
2. Coordinator queries **R = 2 replicas**.
3. Compare versions.
4. Return latest version.
5. Optionally repair outdated replica (read-repair).

---

### 4.4 Conflict Resolution

Use one of:

* Last-write-wins (timestamp)
* Vector clocks (advanced option)

For prototype simplicity:

**Use timestamp-based versioning.**

---

## 5. Implementation Plan

### Phase 1 – Basic Replica Service

**Technology suggestion:**

* Python (Flask or FastAPI)
* In-memory dictionary for storage
* Docker for containerization

Steps:

1. Create replica server.
2. Implement GET and PUT endpoints.
3. Add timestamp to stored values.
4. Test single-node behavior.

---

### Phase 2 – Inter-Replica Communication

1. Add peer configuration list.
2. Implement internal endpoint:

   * `/internal/replicate`
3. On write:

   * Forward to peers.
4. Count acknowledgements.

---

### Phase 3 – Quorum Logic

Implement:

```python
N = 3
W = 2
R = 2
```

For writes:

* Wait until W acknowledgements received.
* Timeout if quorum not met.

For reads:

* Query R replicas.
* Compare timestamps.
* Return latest.

---

### Phase 4 – Docker Deployment

Create:

* `Dockerfile`
* `docker-compose.yml`

Compose file should define:

* 3 services
* Exposed ports (5001–5003)
* Network for internal communication

Example structure:

```
geo-nosql/
│
├── app/
│   └── server.py
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

### Phase 5 – Failure Simulation

Test:

* Stop 1 container → system still operational.
* Stop 2 containers → quorum fails.
* Network delay simulation (optional).

---

## 6. Optional Enhancements

* Read repair mechanism
* Background anti-entropy sync
* Health monitoring endpoint
* Leader–Follower variant
* Raft-based consensus (advanced)
* Persistent storage (SQLite or file-based)
* Region-aware routing (simulate nearest-region reads)

---

## 7. Expected Outcome

The system should demonstrate:

* High availability with 1 node failure
* Eventual consistency
* Read-write overlap guarantee
* Realistic geo-distributed behavior simulation

---

## 8. Learning Objectives

By implementing this prototype, you will understand:

* CAP theorem trade-offs
* Quorum mechanics (R, W, N)
* Distributed failure handling
* Replication strategies
* Consistency tuning
* Container-based distributed simulation