import pytest
import hmac
import hashlib
import json
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def compute_signature(body: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature"""
    return hmac.new(
        secret.encode(),
        body.encode(),
        hashlib.sha256
    ).hexdigest()

def test_webhook_invalid_signature():
    """Test webhook with invalid signature"""
    body = json.dumps({
        "message_id": "test1",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello"
    })
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": "invalid"
        }
    )
    
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid signature"

def test_webhook_valid_insert():
    """Test webhook with valid signature"""
    body = json.dumps({
        "message_id": "test2",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Hello"
    })
    
    signature = compute_signature(body,"testsecret")
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_webhook_duplicate():
    """Test webhook idempotency"""
    body = json.dumps({
        "message_id": "test3",
        "from": "+919876543210",
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z",
        "text": "Duplicate test"
    })
    
    signature = compute_signature(body, settings.webhook_secret or "testsecret")
    
    # First insert
    response1 = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    assert response1.status_code == 200
    
    # Second insert (duplicate)
    response2 = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    assert response2.status_code == 200
    assert response2.json() == {"status": "ok"}

def test_webhook_validation_error():
    """Test webhook with invalid payload"""
    body = json.dumps({
        "message_id": "test4",
        "from": "invalid_phone",  # Invalid E.164 format
        "to": "+14155550100",
        "ts": "2025-01-15T10:00:00Z"
    })
    
    signature = compute_signature(body, settings.webhook_secret or "testsecret")
    
    response = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature
        }
    )
    
    assert response.status_code == 422