# Checkout System Architecture & Flow

This document details the system containers and checkout handshake.

## 1. High-Level Architecture

```graph:arch title="Checkout Topology" id="checkout-topology"
{
  "nodes": [
    {"id": "fe", "name": "Frontend Web", "tag": "UI", "layer": 0},
    {"id": "api", "name": "API Gateway", "tag": "GATEWAY", "layer": 1, "focal": true},
    {"id": "pay", "name": "Payment Svc", "tag": "SVC", "layer": 2},
    {"id": "db", "name": "Postgres DB", "tag": "STORE", "layer": 3}
  ],
  "edges": [
    {"from": "fe", "to": "api", "label": "HTTPS", "proto": "https"},
    {"from": "api", "to": "pay", "label": "Authorize", "focal": true},
    {"from": "pay", "to": "db", "label": "SQL Insert"}
  ]
}
```

## 2. Sequence Diagram

```graph:seq title="Checkout Sequence" id="checkout-seq"
{
  "actors": [
    {"id": "user", "name": "Shopper", "tag": "USER"},
    {"id": "api", "name": "API Gateway", "tag": "GATEWAY", "focal": true},
    {"id": "pay", "name": "Payment Svc", "tag": "SVC"}
  ],
  "messages": [
    {"from": "user", "to": "api", "label": "POST /checkout", "proto": "https"},
    {"from": "api", "to": "pay", "label": "Authorize Card", "focal": true},
    {"from": "pay", "to": "api", "label": "200 Approved", "reply": true}
  ]
}
```
