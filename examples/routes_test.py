from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/orders")
def create_order():
    return {"order_id": 123}

@app.get("/api/v1/orders/{order_id}")
def get_order(order_id: int):
    return {"order_id": order_id}

@app.post("/api/v1/checkout")
def checkout():
    return {"status": "charged"}
