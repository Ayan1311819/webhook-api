# Webhook API Service

A production-ready webhook receiver API with HMAC signature verification, message storage, and Prometheus metrics.

## Quick Start
```bash
git clone https://github.com/Ayan1311819/webhook-api.git
cd webhook-api
cp .env.example .env
```
### Running the Service
**Using Make (Linux/Mac or Windows with make installed):**
```bash
make up

# Or use Docker Compose directly (recommended for Windows)
docker compose up -d --build
```

**Note for Windows users:** If you don't have `make` installed, either:
- Use the `docker compose` commands directly (recommended)
- Install Make via Chocolatey: `choco install make`
- Install Make via WSL (Windows Subsystem for Linux)


**Service URLs:**
- API: http://localhost:8000
- Webhook: http://localhost:8000/webhook
- Messages: http://localhost:8000/messages
- Stats: http://localhost:8000/stats
- Metrics: http://localhost:8000/metrics
- Health (Live): http://localhost:8000/health/live
- Health (Ready): http://localhost:8000/health/ready

### Other Commands

```bash
# View logs
make logs
docker compose logs -f api

# Stop services
make down
docker compose down -v

# Run tests
make test
docker compose exec api pytest tests/ -v
```

## API Endpoints

### 1. POST `/webhook`

Receives webhook messages with HMAC signature verification.

**Headers:**
- `Content-Type: application/json`
- `X-Signature: <hmac_sha256_hex>`

**Body:**
```json
{
  "message_id": "m1",
  "from": "+919876543210",
  "to": "+14155550100",
  "ts": "2025-01-15T10:00:00Z",
  "text": "Hello"
}
```
#This is how I implemented verification
```bash
def verify_signature(body: bytes, signature: str) -> bool:
    """Verify HMAC-SHA256 signature"""
    expected = hmac.new(
        settings.webhook_secret.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    print("Expected signature:", expected)
    print("Received signature:", signature)
    print("Body bytes:", body)
    print("Webhook secret:", repr(settings.webhook_secret))

    return hmac.compare_digest(expected, signature)
```
**Responses:**
- `200` - Message accepted (first time or duplicate)
- `401` - Invalid/missing signature
- `422` - Validation error

**Example:**
```bash
# Compute HMAC-SHA256 signature of raw body
BODY='{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello"}'
SIGNATURE=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "testsecret" | cut -d' ' -f2)

curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIGNATURE" \
  -d "$BODY"
```

---

### 2. GET `/messages`

List stored messages with pagination and filtering.

**Query Parameters:**
- `limit` (optional, default: 10, max: 100) - Messages per page
- `offset` (optional, default: 0) - Number of messages to skip
- `from` (optional) - Filter by sender phone number
- `since` (optional) - ISO-8601 timestamp, return messages with `ts >= since`
- `q` (optional) - Free-text search in message text (case-insensitive)

**Response:**
```json
{
  "data": [
    {
      "message_id": "m1",
      "from": "+919876543210",
      "to": "+14155550100",
      "ts": "2025-01-15T10:00:00Z",
      "text": "Hello"
    }
  ],
  "total": 4,
  "limit": 10,
  "offset": 0
}
```

**Examples:**
```bash
# All messages
curl "http://localhost:8000/messages"

# Pagination
curl "http://localhost:8000/messages?limit=2&offset=0"

# Filter by sender
curl "http://localhost:8000/messages?from=%2B919876543210"

# Filter by timestamp
curl "http://localhost:8000/messages?since=2025-01-15T09:30:00Z"

# Text search
curl "http://localhost:8000/messages?q=Hello"
```

**Ordering:** Messages ordered by `ts ASC, message_id ASC` (oldest first).

---

### 3. GET `/stats`

Message statistics and analytics.

**Response:**
```json
{
  "total_messages": 123,
  "senders_count": 10,
  "messages_per_sender": [
    {"from": "+919876543210", "count": 50},
    {"from": "+911234567890", "count": 30}
  ],
  "first_message_ts": "2025-01-10T09:00:00Z",
  "last_message_ts": "2025-01-15T10:00:00Z"
}
```

**Example:**
```bash
curl http://localhost:8000/stats
```

---

### 4. GET `/metrics`

Prometheus-format metrics.

**Key Metrics:**
- `http_requests_total{path, status}` - Total HTTP requests
- `webhook_requests_total{result}` - Webhook outcomes (created, duplicate, invalid_signature, validation_error)
- `request_latency_ms_bucket` - Request latency histogram

**Example:**
```bash
curl http://localhost:8000/metrics
```

---

### 5. Health Endpoints

**GET `/health/live`**
- Returns `200` if application is running

**GET `/health/ready`**
- Returns `200` if database is ready and `WEBHOOK_SECRET` is set

**Examples:**
```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

---

## Design Decisions

### HMAC Signature Verification

**Implementation:**
- HMAC-SHA256 signature verification using Python's `hmac.compare_digest()`
- Secret key from environment variable `WEBHOOK_SECRET`
- Signature passed as lowercase hex string in `X-Signature` header
- **JSON normalization:** Before verification, the raw body is parsed and normalized (keys quoted, values quoted) to handle pseudo-JSON format, then re-encoded to bytes for HMAC computation

**Why JSON normalization?**
- Handles variations in JSON formatting (unquoted keys, unquoted values)
- Ensures consistent signature verification regardless of input formatting
- The normalized JSON (with proper quoting) is used for HMAC computation
- Falls back to raw body if input is already valid JSON

**Security considerations:**
- Uses `hmac.compare_digest()` for constant-time comparison (prevents timing attacks)
- Returns `401` for invalid signatures without details (no information leakage)
- No database operation on failed signature
- Secret rotation supported via environment variables

---

### Pagination Contract (implemented as per the instructions given)

**Design:** Offset-based pagination with `limit` and `offset` parameters.

**Defaults:**
- `limit`: 10 (max: 100)
- `offset`: 0
- Ordering: `ts ASC, message_id ASC` (deterministic, oldest first)

**Response structure:**
```json
{
  "total": 50,    // Total matching filter (for pagination UI)
  "data": [...],   // Current page
  "limit": 10,     // Echoed back
  "offset": 0      // Echoed back
}
```

---

### Stats & Metrics

**`/stats` Endpoint:**
- **Design:** Computed on-demand from database using SQL aggregations
- **Data provided:**
  - `total_messages` - Overall count
  - `senders_count` - Unique senders
  - `messages_per_sender` - Top 10 senders by message count
  - `first_message_ts` / `last_message_ts` - Time range

**`/metrics` Endpoint:**
- **Purpose:** Technical monitoring for Prometheus/Grafana
- **Format:** Prometheus text exposition format
- **Key metrics:**
  - `http_requests_total` - Tracks all HTTP traffic with path/status labels
  - `webhook_requests_total` - Webhook-specific outcomes (created, duplicate, invalid_signature, validation_error)
  - `request_latency_ms_bucket` - Request latency distribution

**Why separate endpoints?**
- Different audiences: `/stats` for business analysts, `/metrics` for SRE/DevOps
- Different formats: JSON vs Prometheus text format
- Different refresh rates: Stats can be cached, metrics need real-time accuracy

---

## Configuration

**Environment Variables:**

- `WEBHOOK_SECRET` - HMAC secret key (required, no default)
- `DATABASE_URL` - SQLite path (default: `sqlite:////data/app.db`)
- `LOG_LEVEL` - Logging level (default: `INFO`)

**Example:**
```bash
export WEBHOOK_SECRET="testsecret"
export DATABASE_URL="sqlite:////data/app.db"
export LOG_LEVEL="INFO"
```

---

## Logging

All requests emit structured JSON logs with:
- `ts` - Server timestamp (ISO-8601)
- `level` - Log level
- `request_id` - Unique per request
- `method` - HTTP method
- `path` - Request path
- `status` - HTTP status code
- `latency_ms` - Request duration

**Webhook logs include:**
- `message_id` - Message identifier
- `dup` - Boolean, true if duplicate
- `result` - Outcome (created, duplicate, invalid_signature, validation_error)

**View logs:**
```bash
docker compose logs -f api
```

---

## Testing script (I just tried to simulate your tests on my end just to make sure its working)

Run the test script:

```powershell
.\test_webhook.ps1
```

**Coverage:**
- ✅ HMAC signature validation (valid/invalid)
- ✅ Idempotency (duplicate messages)
- ✅ Pagination and filtering
- ✅ Statistics accuracy
- ✅ Metrics exposure
- ✅ Health checks

---

## Project Structure

```
.
├── app/
│   ├── main.py           # FastAPI app & routes
│   ├── models.py         # Database schema
│   ├── storage.py        # Database operations
│   ├── logging_utils.py  # JSON logger
│   ├── metrics.py        # Prometheus metrics
│   └── config.py         # Environment config
├── tests/
│   ├── test_webhook.py   # Webhook tests
│   ├── test_messages.py  # Messages endpoint tests
│   └── test_stats.py     # Stats tests
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── Makefile
├── test_webhook.ps1      # PowerShell test script
└── README.md
```

---

## Setup Used

**Development Environment:**
- VSCode + GitHub Copilot for code assistance
- Occasional ChatGPT prompts for design decisions and documentation
- Docker Desktop for local development and testing

---
