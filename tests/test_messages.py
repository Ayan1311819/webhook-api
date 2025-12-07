import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_messages_basic_list():
    """Test basic message listing"""
    response = client.get("/messages")
    
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert data["limit"] == 10
    assert data["offset"] == 0

def test_messages_pagination():
    """Test message pagination"""
    response = client.get("/messages?limit=2&offset=0")
    
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 2
    assert data["offset"] == 0
    assert len(data["data"]) <= 2

def test_messages_filter_from():
    """Test filtering by from"""
    response = client.get("/messages?from=+919876543210")
    
    assert response.status_code == 200
    data = response.json()
    for msg in data["data"]:
        assert msg["from"] == "+919876543210"

def test_messages_filter_query():
    """Test text search filter"""
    response = client.get("/messages?q=Hello")
    
    assert response.status_code == 200
    # Just check it doesn't error