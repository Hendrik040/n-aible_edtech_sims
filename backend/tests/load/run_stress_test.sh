#!/bin/bash
# Registration Stress Test
# Tests connection pool at maximum capacity with 200 concurrent users
# Usage: ./tests/load/run_stress_test.sh

set -e

echo "=================================================="
echo "⚡ REGISTRATION STRESS TEST"
echo "=================================================="
echo "Simulating: 200 concurrent users"
echo "Duration: 5 minutes"
echo "Spawn rate: 20 users/second"
echo "=================================================="
echo ""
echo "⚠️  WARNING: This will push your system to limits!"
echo "   - Connection pool will hit ~150/150 capacity"
echo "   - Some timeouts are expected and normal"
echo "   - Monitor backend logs for pool warnings"
echo ""

# Create reports directory if it doesn't exist
mkdir -p reports

# Generate timestamp for report filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="reports/stress_test_${TIMESTAMP}.html"

echo "📊 Report will be saved to: ${REPORT_FILE}"
echo ""
echo "Starting test in 5 seconds... (Ctrl+C to cancel)"
sleep 5

# Run the load test
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 200 \
  --spawn-rate 20 \
  --run-time 5m \
  --headless \
  --html "${REPORT_FILE}" \
  --csv "reports/stress_test_${TIMESTAMP}"

echo ""
echo "=================================================="
echo "✅ Stress test completed!"
echo "=================================================="
echo "📊 HTML Report: ${REPORT_FILE}"
echo "📈 CSV Data: reports/stress_test_${TIMESTAMP}_*.csv"
echo ""
echo "Review the report for:"
echo "  - Success rate (should be >90%)"
echo "  - Response times (some slowness expected)"
echo "  - Connection pool warnings in backend logs"
