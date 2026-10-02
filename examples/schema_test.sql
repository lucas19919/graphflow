CREATE TABLE users (
    id UUID PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP
);

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    user_id UUID,
    status VARCHAR(20),
    amount_cents INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
