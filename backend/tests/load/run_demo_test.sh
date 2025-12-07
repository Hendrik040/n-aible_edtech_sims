#!/bin/bash
# Demo Rehearsal Load Test
# Simulates 60 concurrent users for 10 minutes
# Usage: ./tests/load/run_demo_test.sh

set -e

echo "=================================================="
echo "🎯 DEMO REHEARSAL LOAD TEST"
echo "=================================================="
echo "Simulating: 60 concurrent users"
echo "Duration: 10 minutes"
echo "Spawn rate: 12 users/second"
echo "=================================================="
echo ""

# Create reports directory if it doesn't exist
mkdir -p reports

# Generate timestamp for report filename
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="reports/demo_rehearsal_${TIMESTAMP}.html"

echo "📊 Report will be saved to: ${REPORT_FILE}"
echo ""
echo "Starting test in 3 seconds..."
sleep 3

# Run the load test
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 60 \
  --spawn-rate 12 \
  --run-time 10m \
  --headless \
  --html "${REPORT_FILE}" \
  --csv "reports/demo_rehearsal_${TIMESTAMP}"

echo ""
echo "=================================================="
echo "✅ Test completed!"
echo "=================================================="
echo "📊 HTML Report: ${REPORT_FILE}"
echo "📈 CSV Data: reports/demo_rehearsal_${TIMESTAMP}_*.csv"
echo ""
echo "Open the HTML report in your browser to view detailed results."
