# Test 3a: Invalid signature (expect 401)

$SECRET = "testsecret"

# Raw JSON body sent directly
$BODY = '{"message_id":"m1","from":"+919876543210","to":"+14155550100","ts":"2025-01-15T10:00:00Z","text":"Hello"}'

Write-Host "`n--- Test 3a: Invalid signature (expect 401) ---"

# $code = curl.exe -s -o $null -w "%{http_code}" `
#     -H "Content-Type: application/json" `
#     -H "X-Signature: 123" `
#     --data "$BODY" `
#     http://localhost:8000/webhook

$code = curl.exe -s -o response.tmp -w "%{http_code}" `
    -H "Content-Type: application/json" `
    -H "X-Signature: 123" `
    --data "$BODY" `
    http://localhost:8000/webhook

if ($code -eq "401") {
    Write-Host "PASS: Server rejected invalid signature (401)" -ForegroundColor Green
} else {
    Write-Host "FAIL: Expected 401, got $code" -ForegroundColor Red
}


function Compute-HexHmac([string]$secret, [string]$text) {
    $utf8 = [System.Text.Encoding]::UTF8
    $hmac = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = $utf8.GetBytes($secret)
    $hash = $hmac.ComputeHash($utf8.GetBytes($text))
    ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
}
Write-Host "`n--- Test 3b: Computing valid signature from raw body ---"

$VALID_SIG = Compute-HexHmac $SECRET $BODY

Write-Host "  Body:"
Write-Host "  $BODY"

Write-Host "`n  Computed signature:"
Write-Host "  $VALID_SIG"

Write-Host "`n--- Test 3c: Valid signature (expect 200) ---"

$SIG = Compute-HexHmac $SECRET $BODY

Write-Host "Using signature: $SIG"

$code = curl.exe -s -o response.tmp -w "%{http_code}" `
    -H "Content-Type: application/json" `
    -H "X-Signature: $SIG" `
    --data "$BODY" `
    http://localhost:8000/webhook

if ($code -eq "200") {
    Write-Host "PASS: Server accepted valid signature (200)" -ForegroundColor Green
} else {
    Write-Host "FAIL: Expected 200, got $code" -ForegroundColor Red
}

# --- Test 3d: duplicate (resend) ---
Write-Host "`nTest 3d: Duplicate message..."
$result = curl.exe -s -w "`nHTTP_CODE:%{http_code}" `
    -H "Content-Type: application/json" `
    -H "X-Signature: $SIG" `
    --data-binary "$BODY" `
    http://localhost:8000/webhook

Write-Host "  Response: $result"
if ($result -match "200") {
    Write-Host "  VALID: Duplicate handled correctly (200)" -ForegroundColor Green
} else {
    Write-Host "  FAIL: Duplicate test failed" -ForegroundColor Red
}

# --- Step 4: Seed more messages with Send-Message function ---
Write-Host "`n[Step 4] Seeding more messages..." -ForegroundColor Yellow

function Send-Message {
    param($MessageId, $From, $To, $Ts, $Text)

    # Build JSON manually to ensure exact format
    $body = '{' +
            '"message_id":"' + $MessageId + '",' +
            '"from":"' + $From + '",' +
            '"to":"' + $To + '",' +
            '"ts":"' + $Ts + '",' +
            '"text":"' + $Text + '"' +
            '}'

    # Compute signature
    $sig = Compute-HexHmac $SECRET $body

    # Send directly (no temp file)
    curl.exe -s `
        -H "Content-Type: application/json" `
        -H "X-Signature: $sig" `
        --data "$body" `
        http://localhost:8000/webhook | Out-Null

    Write-Host "  Sent: $MessageId"
}

Send-Message "m2" "+919876543210" "+14155550100" "2025-01-15T09:00:00Z" "Earlier"
Send-Message "m3" "+911234567890" "+14155550100" "2025-01-15T09:30:00Z" "Different sender"
Send-Message "m4" "+919876543210" "+14155550100" "2025-01-15T11:00:00Z" "Later message"

Write-Host "Messages seeded" -ForegroundColor Green

# --- Step 5: Test /messages endpoint ---
Write-Host "`n[Step 5] Testing /messages endpoint..." -ForegroundColor Yellow

Write-Host "`n  Basic list:"
$all = curl.exe -s "http://localhost:8000/messages" | ConvertFrom-Json
Write-Host "  Total messages: $($all.total)"
Write-Host "  Returned: $($all.data.Count) items"

# Print full list
Write-Host "`n  Full message list (raw):"
$all.data | ForEach-Object {
    Write-Host "    - $($_ | ConvertTo-Json -Compress)"
}

Write-Host "`n  Pagination (limit=2, offset=0):"
$limited = curl.exe -s "http://localhost:8000/messages?limit=2&offset=0" | ConvertFrom-Json
Write-Host "  Returned: $($limited.data.Count) items (expected 2)"

Write-Host "`n  Filter by sender (+919876543210):"
$filtered = curl.exe -s "http://localhost:8000/messages?from=%2B919876543210" | ConvertFrom-Json
Write-Host "  Total: $($filtered.total) messages"

# Print filtered list too
Write-Host "  Filtered messages:"
$filtered.data | ForEach-Object {
    Write-Host "    - $($_ | ConvertTo-Json -Compress)"
}

# --- Step 6: Test /stats endpoint ---
Write-Host "`n[Step 6] Testing /stats endpoint..." -ForegroundColor Yellow
$stats = curl.exe -s "http://localhost:8000/stats" | ConvertFrom-Json
Write-Host "  Total messages: $($stats.total_messages)"
Write-Host "  Senders count: $($stats.senders_count)"

# Verify sum
$sum = ($stats.messages_per_sender | Measure-Object -Property count -Sum).Sum
if ($sum -eq $stats.total_messages) {
    Write-Host "  VALID: Sum matches total" -ForegroundColor Green
} else {
    Write-Host "  FAIL: Sum ($sum) doesn't match total ($($stats.total_messages))" -ForegroundColor Red
}

# --- Step 7: Test /metrics endpoint ---
Write-Host "`n[Step 7] Testing /metrics endpoint..." -ForegroundColor Yellow
$metrics = curl.exe -s "http://localhost:8000/metrics"

if ($metrics -match "http_requests_total") {
    Write-Host "  VALID: Found http_requests_total" -ForegroundColor Green
} else {
    Write-Host "  FAIL: Missing http_requests_total" -ForegroundColor Red
}

if ($metrics -match "webhook_requests_total") {
    Write-Host "  VALID: Found webhook_requests_total" -ForegroundColor Green
} else {
    Write-Host "  FAIL: Missing webhook_requests_total" -ForegroundColor Red
}

# --- Step 8: Check logs ---
Write-Host "`n[Step 8] Checking logs..." -ForegroundColor Yellow
Write-Host "  Last 20 log lines:"
docker compose logs api --tail=20 | ForEach-Object { 
    # Use simple string check instead of complex regex to avoid quoting issues
    if ($_ -match "message_id") {
        Write-Host "    [JSON] $_" -ForegroundColor Gray
    } else {
        Write-Host "    $_" -ForegroundColor DarkGray
    }
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "TESTS COMPLETE" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

