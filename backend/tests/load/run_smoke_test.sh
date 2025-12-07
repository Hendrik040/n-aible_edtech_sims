#!/bin/bash
# Quick Smoke Test
# Fast verification that everything works (10 users, 1 minute)
# Usage: ./tests/load/run_smoke_test.sh

set -e

echo "=================================================="
echo "🔥 QUICK SMOKE TEST (AUTH MODULE ONLY)"
echo "=================================================="
echo "Simulating: 10 concurrent users"
echo "Duration: 1 minute"
echo "Spawn rate: 5 users/second"
echo "Testing: Authentication endpoints only"
echo "=================================================="
echo ""
echo "This is a quick health check for auth system"
echo ""

# Create reports directory if it doesn't exist
mkdir -p reports

# Generate timestamp for report filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "Starting test..."
echo ""

# Run the load test
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 10 \
  --spawn-rate 5 \
  --run-time 1m \
  --headless

echo ""
echo "=================================================="
echo "✅ Smoke test completed!"
echo "=================================================="
echo ""
echo "If success rate is >95%, you're good to go!"
echo "If you see failures, check backend logs for errors."
