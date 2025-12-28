#!/usr/bin/env python3
"""
Multi-Region Benchmark Runner

Runs load tests against multiple regions sequentially and generates
a comparison dashboard with performance metrics.

Usage:
    python multi_region_benchmark.py
    python multi_region_benchmark.py --regions EU US-DEV
    python multi_region_benchmark.py --users 30 --duration 2m --parallel
"""

import os
import sys
import json
import subprocess
import argparse
import csv
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import tempfile
import time
import concurrent.futures

# Database support (optional)
try:
    import psycopg2
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import REGION_URLS, VALID_REGIONS, get_url_for_region, LoadTestConfig

# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_REGIONS = ["EU", "US-DEV", "US-EXP"]
DEFAULT_USERS = 30
DEFAULT_SPAWN_RATE = 5
DEFAULT_DURATION = "2m"
REPORTS_DIR = Path(__file__).parent / "reports"


# =============================================================================
# CSV PARSING HELPERS
# =============================================================================

def parse_csv_stats(csv_path: str) -> List[Dict]:
    """
    Parse Locust CSV stats file into a list of dictionaries.
    
    Locust CSV format:
    Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time,
    Min Response Time,Max Response Time,Average Content Size,Requests/s,Failures/s,
    50%,66%,75%,80%,90%,95%,98%,99%,99.9%,99.99%,100%
    """
    stats = []
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats.append({
                    "name": row.get("Name", ""),
                    "method": row.get("Type", ""),
                    "num_requests": int(row.get("Request Count", 0) or 0),
                    "num_failures": int(row.get("Failure Count", 0) or 0),
                    "median_response_time": float(row.get("Median Response Time", 0) or 0),
                    "avg_response_time": float(row.get("Average Response Time", 0) or 0),
                    "min_response_time": float(row.get("Min Response Time", 0) or 0),
                    "max_response_time": float(row.get("Max Response Time", 0) or 0),
                    "current_rps": float(row.get("Requests/s", 0) or 0),
                    "p50": float(row.get("50%", 0) or 0),
                    "p90": float(row.get("90%", 0) or 0),
                    "p95": float(row.get("95%", 0) or 0),
                    "p99": float(row.get("99%", 0) or 0),
                })
    except Exception as e:
        print(f"   Error parsing CSV: {e}")
        return []
    return stats


def parse_stats_from_output(output: str) -> Optional[Dict[str, Any]]:
    """
    Try to parse stats from Locust terminal output as fallback.
    
    Looks for the Aggregated line like:
    Aggregated     341   93(27.27%) |  21120    1605   90193  23000 |    1.14        0.31
    """
    # Look for Aggregated stats line
    pattern = r'Aggregated\s+(\d+)\s+(\d+)\([^)]+\)\s*\|\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
    match = re.search(pattern, output)
    
    if match:
        return {
            "total_requests": int(match.group(1)),
            "total_failures": int(match.group(2)),
            "avg_response_time": float(match.group(3)),
            "min_response_time": float(match.group(4)),
            "max_response_time": float(match.group(5)),
            "median_response_time": float(match.group(6)),
        }
    
    return None


@dataclass
class RegionResult:
    """Results from a single region test."""
    region: str
    url: str
    timestamp: str
    duration_seconds: int
    total_users: int
    spawn_rate: float
    
    # Request metrics
    total_requests: int = 0
    total_failures: int = 0
    failure_rate: float = 0.0
    requests_per_second: float = 0.0
    
    # Response time metrics (ms)
    avg_response_time: float = 0.0
    min_response_time: float = 0.0
    max_response_time: float = 0.0
    median_response_time: float = 0.0
    p90_response_time: float = 0.0
    p95_response_time: float = 0.0
    p99_response_time: float = 0.0
    
    # Per-endpoint data
    endpoints: Dict = None
    
    # Status
    success: bool = True
    error_message: str = ""
    
    def __post_init__(self):
        if self.endpoints is None:
            self.endpoints = {}


def parse_duration(duration_str: str) -> int:
    """Convert duration string (e.g., '2m', '30s', '1h') to seconds."""
    duration_str = duration_str.strip().lower()
    if duration_str.endswith('s'):
        return int(duration_str[:-1])
    elif duration_str.endswith('m'):
        return int(duration_str[:-1]) * 60
    elif duration_str.endswith('h'):
        return int(duration_str[:-1]) * 3600
    else:
        return int(duration_str)


def run_single_region_test(
    region: str,
    users: int,
    spawn_rate: float,
    duration: str,
    scenario: str = "chat_load_test.py"
) -> RegionResult:
    """
    Run a load test against a single region.
    
    Returns RegionResult with all metrics.
    """
    print(f"\n{'='*60}")
    print(f"🌍 Testing Region: {region}")
    print(f"{'='*60}")
    
    try:
        url = get_url_for_region(region)
    except ValueError as e:
        return RegionResult(
            region=region,
            url="",
            timestamp=datetime.now().isoformat(),
            duration_seconds=parse_duration(duration),
            total_users=users,
            spawn_rate=spawn_rate,
            success=False,
            error_message=str(e)
        )
    
    print(f"   URL: {url}")
    print(f"   Users: {users}, Spawn Rate: {spawn_rate}/s, Duration: {duration}")
    
    # Create temp directory for CSV stats
    temp_dir = tempfile.mkdtemp(prefix="locust_")
    csv_prefix = os.path.join(temp_dir, "stats")
    
    # Build locust command
    scenario_path = Path(__file__).parent / "scenarios" / scenario
    
    # Set environment variable for region
    env = os.environ.copy()
    env["TARGET_REGION"] = region
    env["LOAD_TEST_URL"] = url  # Also set URL directly for compatibility
    
    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(scenario_path),
        "--headless",
        "-u", str(users),
        "-r", str(spawn_rate),
        "-t", duration,
        f"--csv={csv_prefix}",
        "--only-summary"
    ]
    
    print(f"   Running test...")
    start_time = time.time()
    
    try:
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=parse_duration(duration) + 120  # Extra time for startup/shutdown
        )
        
        elapsed = time.time() - start_time
        print(f"   Completed in {elapsed:.1f}s")
        
        # Parse CSV stats file
        stats_file = f"{csv_prefix}_stats.csv"
        if os.path.exists(stats_file):
            stats_data = parse_csv_stats(stats_file)
            if stats_data:
                print(f"   ✓ Parsed {len(stats_data)} endpoint stats")
                return parse_locust_stats(region, url, stats_data, users, spawn_rate, duration)
        
        # Fallback: try to parse from stdout/stderr
        print(f"   ⚠ Could not parse CSV stats, trying stderr...")
        parsed_result = parse_stats_from_output(result.stderr or result.stdout or "")
        if parsed_result:
            return RegionResult(
                region=region,
                url=url,
                timestamp=datetime.now().isoformat(),
                duration_seconds=parse_duration(duration),
                total_users=users,
                spawn_rate=spawn_rate,
                **parsed_result,
                success=True
            )
        
        return RegionResult(
            region=region,
            url=url,
            timestamp=datetime.now().isoformat(),
            duration_seconds=parse_duration(duration),
            total_users=users,
            spawn_rate=spawn_rate,
            success=True,
            error_message="Stats parsing failed - test may have run but no metrics captured"
        )
            
    except subprocess.TimeoutExpired:
        return RegionResult(
            region=region,
            url=url,
            timestamp=datetime.now().isoformat(),
            duration_seconds=parse_duration(duration),
            total_users=users,
            spawn_rate=spawn_rate,
            success=False,
            error_message="Test timed out"
        )
    except Exception as e:
        return RegionResult(
            region=region,
            url=url,
            timestamp=datetime.now().isoformat(),
            duration_seconds=parse_duration(duration),
            total_users=users,
            spawn_rate=spawn_rate,
            success=False,
            error_message=str(e)
        )
    finally:
        # Cleanup temp directory
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass


def parse_locust_stats(
    region: str,
    url: str,
    stats_data: List[Dict],
    users: int,
    spawn_rate: float,
    duration: str
) -> RegionResult:
    """Parse Locust CSV/JSON stats into RegionResult."""
    
    # Find the aggregated stats (name = "Aggregated")
    aggregated = None
    endpoints = {}
    
    for entry in stats_data:
        name = entry.get("name", "")
        if name == "Aggregated":
            aggregated = entry
        elif name:  # Skip empty names
            endpoints[name] = {
                "method": entry.get("method", ""),
                "requests": entry.get("num_requests", 0),
                "failures": entry.get("num_failures", 0),
                "avg_response_time": entry.get("avg_response_time", 0),
                "min_response_time": entry.get("min_response_time", 0),
                "max_response_time": entry.get("max_response_time", 0),
                "median_response_time": entry.get("median_response_time", 0),
                # Handle both CSV format (p95) and JSON format (response_times.0.95)
                "p95_response_time": entry.get("p95", 0) or entry.get("response_times", {}).get("0.95", 0),
                "p99_response_time": entry.get("p99", 0) or entry.get("response_times", {}).get("0.99", 0),
            }
    
    if not aggregated:
        # Use first entry if no aggregated
        aggregated = stats_data[0] if stats_data else {}
    
    total_requests = aggregated.get("num_requests", 0)
    total_failures = aggregated.get("num_failures", 0)
    
    # Handle both CSV format (p90, p95, p99) and JSON format (response_times dict)
    response_times = aggregated.get("response_times", {})
    p90 = aggregated.get("p90", 0) or response_times.get("0.90", 0)
    p95 = aggregated.get("p95", 0) or response_times.get("0.95", 0)
    p99 = aggregated.get("p99", 0) or response_times.get("0.99", 0)
    
    return RegionResult(
        region=region,
        url=url,
        timestamp=datetime.now().isoformat(),
        duration_seconds=parse_duration(duration),
        total_users=users,
        spawn_rate=spawn_rate,
        total_requests=total_requests,
        total_failures=total_failures,
        failure_rate=round((total_failures / total_requests * 100) if total_requests > 0 else 0, 2),
        requests_per_second=aggregated.get("current_rps", 0) or aggregated.get("total_rps", 0),
        avg_response_time=round(aggregated.get("avg_response_time", 0), 2),
        min_response_time=round(aggregated.get("min_response_time", 0), 2),
        max_response_time=round(aggregated.get("max_response_time", 0), 2),
        median_response_time=round(aggregated.get("median_response_time", 0), 2),
        p90_response_time=round(p90, 2),
        p95_response_time=round(p95, 2),
        p99_response_time=round(p99, 2),
        endpoints=endpoints,
        success=True
    )


def run_all_regions(
    regions: List[str],
    users: int,
    spawn_rate: float,
    duration: str,
    parallel: bool = False
) -> List[RegionResult]:
    """
    Run tests against all specified regions.
    
    Args:
        regions: List of region codes
        users: Number of concurrent users
        spawn_rate: Users spawned per second
        duration: Test duration (e.g., "2m")
        parallel: If True, run tests in parallel (not recommended)
    
    Returns:
        List of RegionResult objects
    """
    results = []
    
    if parallel:
        print("\n⚠ Running in PARALLEL mode - results may be affected by local resource contention")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(regions)) as executor:
            futures = {
                executor.submit(run_single_region_test, region, users, spawn_rate, duration): region
                for region in regions
            }
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
    else:
        print("\n📋 Running tests SEQUENTIALLY for accurate comparison")
        for i, region in enumerate(regions, 1):
            print(f"\n[{i}/{len(regions)}] Starting test for {region}...")
            result = run_single_region_test(region, users, spawn_rate, duration)
            results.append(result)
            
            # Small delay between tests
            if i < len(regions):
                print(f"   Waiting 5s before next region...")
                time.sleep(5)
    
    return results


def generate_dashboard(results: List[RegionResult], output_path: Path) -> str:
    """
    Generate an HTML dashboard comparing all region results.
    
    Returns the path to the generated HTML file.
    """
    
    # Prepare data for charts
    regions = [r.region for r in results]
    avg_times = [r.avg_response_time for r in results]
    median_times = [r.median_response_time for r in results]
    p90_times = [r.p90_response_time for r in results]  # Added missing p90
    p95_times = [r.p95_response_time for r in results]
    p99_times = [r.p99_response_time for r in results]
    failure_rates = [r.failure_rate for r in results]
    rps = [r.requests_per_second for r in results]
    total_requests = [r.total_requests for r in results]
    
    # Region colors
    colors = {
        "EU": "#3498db",      # Blue
        "US-DEV": "#2ecc71",  # Green
        "US-EXP": "#e74c3c",  # Red
        "US-PROD": "#9b59b6", # Purple
        "US-STAG": "#f39c12", # Orange
    }
    
    region_colors = [colors.get(r, "#95a5a6") for r in regions]
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    test_config = results[0] if results else None
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Region Load Test Comparison</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            color: #e8e8e8;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 30px;
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            backdrop-filter: blur(10px);
        }}
        
        h1 {{
            font-size: 2.5em;
            background: linear-gradient(120deg, #00d4ff, #7c3aed, #f472b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        
        .subtitle {{
            color: #a0a0a0;
            font-size: 1.1em;
        }}
        
        .test-info {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        
        .info-badge {{
            background: rgba(255,255,255,0.1);
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9em;
        }}
        
        .info-badge span {{
            color: #00d4ff;
            font-weight: 600;
        }}
        
        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.1);
        }}
        
        .card h2 {{
            font-size: 1.2em;
            margin-bottom: 20px;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        .card h2::before {{
            content: '';
            width: 4px;
            height: 20px;
            background: linear-gradient(180deg, #00d4ff, #7c3aed);
            border-radius: 2px;
        }}
        
        .chart-container {{
            position: relative;
            height: 300px;
        }}
        
        .summary-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}
        
        .summary-table th,
        .summary-table td {{
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        .summary-table th {{
            color: #a0a0a0;
            font-weight: 500;
            font-size: 0.85em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .summary-table tr:hover {{
            background: rgba(255,255,255,0.05);
        }}
        
        .region-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-weight: 600;
            font-size: 0.9em;
        }}
        
        .metric-good {{ color: #2ecc71; }}
        .metric-warning {{ color: #f39c12; }}
        .metric-bad {{ color: #e74c3c; }}
        
        .winner {{
            background: linear-gradient(120deg, #00d4ff22, #7c3aed22);
            border-left: 3px solid #00d4ff;
        }}
        
        .full-width {{
            grid-column: 1 / -1;
        }}
        
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 0.9em;
        }}
        
        @media (max-width: 768px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}
            
            h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🌍 Multi-Region Load Test Comparison</h1>
            <p class="subtitle">Performance benchmark across different geographical regions</p>
            <div class="test-info">
                <div class="info-badge">📅 <span>{timestamp}</span></div>
                <div class="info-badge">👥 <span>{test_config.total_users if test_config else 'N/A'} users</span></div>
                <div class="info-badge">⏱️ <span>{test_config.duration_seconds if test_config else 'N/A'}s duration</span></div>
                <div class="info-badge">🚀 <span>{test_config.spawn_rate if test_config else 'N/A'}/s spawn rate</span></div>
            </div>
        </header>
        
        <div class="dashboard-grid">
            <!-- Response Time Comparison -->
            <div class="card">
                <h2>Response Time Comparison</h2>
                <div class="chart-container">
                    <canvas id="responseTimeChart"></canvas>
                </div>
            </div>
            
            <!-- Failure Rate & RPS -->
            <div class="card">
                <h2>Reliability & Throughput</h2>
                <div class="chart-container">
                    <canvas id="reliabilityChart"></canvas>
                </div>
            </div>
            
            <!-- Percentile Distribution -->
            <div class="card">
                <h2>Response Time Percentiles</h2>
                <div class="chart-container">
                    <canvas id="percentileChart"></canvas>
                </div>
            </div>
            
            <!-- Total Requests -->
            <div class="card">
                <h2>Total Requests Processed</h2>
                <div class="chart-container">
                    <canvas id="requestsChart"></canvas>
                </div>
            </div>
            
            <!-- Summary Table -->
            <div class="card full-width">
                <h2>Detailed Comparison</h2>
                <table class="summary-table">
                    <thead>
                        <tr>
                            <th>Region</th>
                            <th>URL</th>
                            <th>Requests</th>
                            <th>Failures</th>
                            <th>Failure %</th>
                            <th>Avg (ms)</th>
                            <th>Median (ms)</th>
                            <th>P95 (ms)</th>
                            <th>P99 (ms)</th>
                            <th>RPS</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(generate_table_row(r, results) for r in results)}
                    </tbody>
                </table>
            </div>
        </div>
        
        <footer>
            Generated by n-aible Multi-Region Benchmark Tool
        </footer>
    </div>
    
    <script>
        // Chart.js global config
        Chart.defaults.color = '#a0a0a0';
        Chart.defaults.borderColor = 'rgba(255,255,255,0.1)';
        
        const regions = {json.dumps(regions)};
        const regionColors = {json.dumps(region_colors)};
        
        // Response Time Chart
        new Chart(document.getElementById('responseTimeChart'), {{
            type: 'bar',
            data: {{
                labels: regions,
                datasets: [{{
                    label: 'Average',
                    data: {json.dumps(avg_times)},
                    backgroundColor: regionColors.map(c => c + '99'),
                    borderColor: regionColors,
                    borderWidth: 2
                }}, {{
                    label: 'Median',
                    data: {json.dumps(median_times)},
                    backgroundColor: regionColors.map(c => c + '55'),
                    borderColor: regionColors,
                    borderWidth: 2
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'top' }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{ display: true, text: 'Response Time (ms)' }}
                    }}
                }}
            }}
        }});
        
        // Reliability Chart
        new Chart(document.getElementById('reliabilityChart'), {{
            type: 'bar',
            data: {{
                labels: regions,
                datasets: [{{
                    label: 'Failure Rate (%)',
                    data: {json.dumps(failure_rates)},
                    backgroundColor: '#e74c3c99',
                    borderColor: '#e74c3c',
                    borderWidth: 2,
                    yAxisID: 'y'
                }}, {{
                    label: 'Requests/sec',
                    data: {json.dumps(rps)},
                    backgroundColor: '#2ecc7199',
                    borderColor: '#2ecc71',
                    borderWidth: 2,
                    yAxisID: 'y1'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'top' }}
                }},
                scales: {{
                    y: {{
                        type: 'linear',
                        position: 'left',
                        beginAtZero: true,
                        title: {{ display: true, text: 'Failure Rate (%)' }}
                    }},
                    y1: {{
                        type: 'linear',
                        position: 'right',
                        beginAtZero: true,
                        title: {{ display: true, text: 'Requests/sec' }},
                        grid: {{ drawOnChartArea: false }}
                    }}
                }}
            }}
        }});
        
        // Percentile Chart
        new Chart(document.getElementById('percentileChart'), {{
            type: 'line',
            data: {{
                labels: ['Median', 'P90', 'P95', 'P99'],
                datasets: regions.map((region, i) => ({{
                    label: region,
                    data: [
                        {json.dumps(median_times)}[i],
                        {json.dumps(p90_times)}[i],
                        {json.dumps(p95_times)}[i],
                        {json.dumps(p99_times)}[i]
                    ],
                    borderColor: regionColors[i],
                    backgroundColor: regionColors[i] + '33',
                    fill: true,
                    tension: 0.3
                }}))
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'top' }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        title: {{ display: true, text: 'Response Time (ms)' }}
                    }}
                }}
            }}
        }});
        
        // Total Requests Chart
        new Chart(document.getElementById('requestsChart'), {{
            type: 'doughnut',
            data: {{
                labels: regions,
                datasets: [{{
                    data: {json.dumps(total_requests)},
                    backgroundColor: regionColors,
                    borderColor: '#1a1a2e',
                    borderWidth: 3
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'right' }}
                }}
            }}
        }});
    </script>
</body>
</html>
'''
    
    # Write HTML file
    output_file = output_path / f"multi_region_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    output_file.write_text(html)
    
    return str(output_file)


def generate_table_row(result: RegionResult, all_results: List[RegionResult]) -> str:
    """Generate HTML table row for a result."""
    
    # Find best values for highlighting
    best_avg = min(r.avg_response_time for r in all_results if r.success)
    best_failure = min(r.failure_rate for r in all_results if r.success)
    
    is_winner = (result.avg_response_time == best_avg and result.failure_rate == best_failure)
    
    # Color classes based on values
    def get_metric_class(value, best, higher_is_worse=True):
        if higher_is_worse:
            if value <= best * 1.1:
                return "metric-good"
            elif value <= best * 1.5:
                return "metric-warning"
            else:
                return "metric-bad"
        else:
            if value >= best * 0.9:
                return "metric-good"
            elif value >= best * 0.5:
                return "metric-warning"
            else:
                return "metric-bad"
    
    colors = {
        "EU": "#3498db",
        "US-DEV": "#2ecc71",
        "US-EXP": "#e74c3c",
        "US-PROD": "#9b59b6",
        "US-STAG": "#f39c12",
    }
    
    color = colors.get(result.region, "#95a5a6")
    winner_class = "winner" if is_winner else ""
    
    if not result.success:
        return f'''
        <tr class="{winner_class}">
            <td><span class="region-badge" style="background: {color}22; color: {color}">{result.region}</span></td>
            <td colspan="9" style="color: #e74c3c;">❌ {result.error_message}</td>
        </tr>
        '''
    
    return f'''
    <tr class="{winner_class}">
        <td><span class="region-badge" style="background: {color}22; color: {color}">{result.region}</span></td>
        <td style="font-size: 0.8em; color: #888;">{result.url[:40]}...</td>
        <td>{result.total_requests:,}</td>
        <td class="{get_metric_class(result.total_failures, 0)}">{result.total_failures}</td>
        <td class="{get_metric_class(result.failure_rate, best_failure)}">{result.failure_rate:.1f}%</td>
        <td class="{get_metric_class(result.avg_response_time, best_avg)}">{result.avg_response_time:.0f}</td>
        <td>{result.median_response_time:.0f}</td>
        <td>{result.p95_response_time:.0f}</td>
        <td>{result.p99_response_time:.0f}</td>
        <td class="{get_metric_class(result.requests_per_second, max(r.requests_per_second for r in all_results), higher_is_worse=False)}">{result.requests_per_second:.1f}</td>
    </tr>
    '''


def save_results_to_json(results: List[RegionResult], output_path: Path) -> str:
    """Save results to JSON file for later analysis."""
    output_file = output_path / f"multi_region_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    data = {
        "timestamp": datetime.now().isoformat(),
        "results": [asdict(r) for r in results]
    }
    
    output_file.write_text(json.dumps(data, indent=2))
    return str(output_file)


# =============================================================================
# DATABASE SAVING
# =============================================================================

def get_git_info() -> Dict[str, Optional[str]]:
    """Get current git commit and branch."""
    git_info = {"commit": None, "branch": None}
    
    try:
        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            git_info["commit"] = result.stdout.strip()[:40]
        
        # Get current branch name
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            git_info["branch"] = result.stdout.strip()[:100]
    except Exception:
        pass
    
    return git_info


def save_results_to_database(
    results: List[RegionResult],
    test_scenario: str = "multi_region_benchmark",
    configuration_notes: Optional[str] = None
) -> Optional[List[int]]:
    """
    Save benchmark results to PostgreSQL database.
    
    Args:
        results: List of RegionResult objects
        test_scenario: Name of the test scenario
        configuration_notes: Optional notes about this test run
        
    Returns:
        List of inserted run IDs, or None if save failed
    """
    if not HAS_PSYCOPG2:
        print("⚠ psycopg2 not installed - skipping database save")
        print("   Install with: pip install psycopg2-binary")
        return None
    
    # Get database URL from environment
    database_url = os.getenv("LOADTEST_DATABASE_URL")
    if not database_url:
        print("⚠ LOADTEST_DATABASE_URL not set - skipping database save")
        return None
    
    # Get git info
    git_info = get_git_info()
    
    # Get test runner location from environment
    runner_location = os.getenv("TEST_RUNNER_LOCATION", "Unknown")
    environment = os.getenv("LOAD_TEST_ENVIRONMENT", "unknown")
    
    inserted_ids = []
    
    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        for result in results:
            # Insert into load_test_runs
            cur.execute("""
                INSERT INTO load_test_runs (
                    target_region, target_url, test_runner_location, environment,
                    git_commit, git_branch,
                    test_scenario, configuration_notes,
                    total_users, spawn_rate, run_duration_seconds,
                    total_requests, total_failures, failure_rate_percent,
                    avg_response_time_ms, min_response_time_ms, max_response_time_ms,
                    median_response_time_ms, p90_response_time_ms, p95_response_time_ms, p99_response_time_ms,
                    requests_per_second
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s
                ) RETURNING id
            """, (
                result.region,
                result.url,
                runner_location,
                environment,
                git_info["commit"],
                git_info["branch"],
                test_scenario,
                configuration_notes or result.error_message if not result.success else configuration_notes,
                result.total_users,
                result.spawn_rate,
                result.duration_seconds,
                result.total_requests,
                result.total_failures,
                result.failure_rate,
                result.avg_response_time,
                result.min_response_time,
                result.max_response_time,
                result.median_response_time,
                result.p90_response_time,
                result.p95_response_time,
                result.p99_response_time,
                result.requests_per_second
            ))
            
            run_id = cur.fetchone()[0]
            inserted_ids.append(run_id)
            
            # Insert endpoint results if available
            if result.endpoints:
                for endpoint_name, endpoint_data in result.endpoints.items():
                    requests = endpoint_data.get("requests", 0)
                    failures = endpoint_data.get("failures", 0)
                    failure_rate = (failures / requests * 100) if requests > 0 else 0
                    
                    cur.execute("""
                        INSERT INTO load_test_endpoint_results (
                            load_test_run_id,
                            endpoint_name, http_method,
                            total_requests, total_failures, failure_rate_percent,
                            avg_response_time_ms, min_response_time_ms, max_response_time_ms,
                            median_response_time_ms, p95_response_time_ms, p99_response_time_ms
                        ) VALUES (
                            %s,
                            %s, %s,
                            %s, %s, %s,
                            %s, %s, %s,
                            %s, %s, %s
                        )
                    """, (
                        run_id,
                        endpoint_name,
                        endpoint_data.get("method", ""),
                        requests,
                        failures,
                        failure_rate,
                        endpoint_data.get("avg_response_time", 0),
                        endpoint_data.get("min_response_time", 0),
                        endpoint_data.get("max_response_time", 0),
                        endpoint_data.get("median_response_time", 0),
                        endpoint_data.get("p95_response_time", 0),
                        endpoint_data.get("p99_response_time", 0)
                    ))
        
        conn.commit()
        print(f"✓ Results saved to database (run_ids: {inserted_ids})")
        return inserted_ids
        
    except Exception as e:
        print(f"✗ Failed to save to database: {e}")
        if 'conn' in locals():
            conn.rollback()
        return None
        
    finally:
        if 'cur' in locals():
            cur.close()
        if 'conn' in locals():
            conn.close()


def print_summary(results: List[RegionResult]):
    """Print a summary of results to console."""
    print("\n" + "=" * 80)
    print("📊 MULTI-REGION BENCHMARK SUMMARY")
    print("=" * 80)
    
    successful = [r for r in results if r.success]
    
    if not successful:
        print("❌ No successful tests!")
        return
    
    # Find winner (lowest avg response time with acceptable failure rate)
    winner = min(successful, key=lambda r: r.avg_response_time if r.failure_rate < 10 else float('inf'))
    
    print(f"\n🏆 WINNER: {winner.region}")
    print(f"   Average Response Time: {winner.avg_response_time:.0f}ms")
    print(f"   Failure Rate: {winner.failure_rate:.1f}%")
    print(f"   Requests/sec: {winner.requests_per_second:.1f}")
    
    print("\n📈 All Results:")
    print("-" * 80)
    print(f"{'Region':<12} {'Avg (ms)':<12} {'Median (ms)':<12} {'P95 (ms)':<12} {'Fail %':<10} {'RPS':<10}")
    print("-" * 80)
    
    for r in sorted(successful, key=lambda x: x.avg_response_time):
        marker = "👑" if r == winner else "  "
        print(f"{marker}{r.region:<10} {r.avg_response_time:<12.0f} {r.median_response_time:<12.0f} {r.p95_response_time:<12.0f} {r.failure_rate:<10.1f} {r.requests_per_second:<10.1f}")
    
    for r in results:
        if not r.success:
            print(f"❌ {r.region:<10} FAILED: {r.error_message}")


def main():
    parser = argparse.ArgumentParser(
        description="Run load tests against multiple regions and generate comparison dashboard"
    )
    parser.add_argument(
        "--regions", "-r",
        nargs="+",
        default=DEFAULT_REGIONS,
        choices=VALID_REGIONS,
        help=f"Regions to test (default: {DEFAULT_REGIONS})"
    )
    parser.add_argument(
        "--users", "-u",
        type=int,
        default=DEFAULT_USERS,
        help=f"Number of concurrent users (default: {DEFAULT_USERS})"
    )
    parser.add_argument(
        "--spawn-rate", "-s",
        type=float,
        default=DEFAULT_SPAWN_RATE,
        help=f"Users spawned per second (default: {DEFAULT_SPAWN_RATE})"
    )
    parser.add_argument(
        "--duration", "-t",
        type=str,
        default=DEFAULT_DURATION,
        help=f"Test duration e.g. 2m, 30s, 1h (default: {DEFAULT_DURATION})"
    )
    parser.add_argument(
        "--parallel", "-p",
        action="store_true",
        help="Run tests in parallel (not recommended for accurate comparison)"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="chat_load_test.py",
        help="Scenario file to run (default: chat_load_test.py)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 80)
    print("🚀 N-AIBLE MULTI-REGION BENCHMARK")
    print("=" * 80)
    print(f"   Regions:     {', '.join(args.regions)}")
    print(f"   Users:       {args.users}")
    print(f"   Spawn Rate:  {args.spawn_rate}/s")
    print(f"   Duration:    {args.duration}")
    print(f"   Mode:        {'Parallel' if args.parallel else 'Sequential'}")
    print(f"   Scenario:    {args.scenario}")
    print("=" * 80)
    
    # Ensure reports directory exists
    REPORTS_DIR.mkdir(exist_ok=True)
    
    # Run tests
    results = run_all_regions(
        regions=args.regions,
        users=args.users,
        spawn_rate=args.spawn_rate,
        duration=args.duration,
        parallel=args.parallel
    )
    
    # Print summary
    print_summary(results)
    
    # Save results to files
    json_file = save_results_to_json(results, REPORTS_DIR)
    print(f"\n📁 JSON results saved to: {json_file}")
    
    # Generate dashboard
    dashboard_file = generate_dashboard(results, REPORTS_DIR)
    print(f"📊 Dashboard saved to: {dashboard_file}")
    
    # Save to database
    save_results_to_database(
        results,
        test_scenario=args.scenario.replace(".py", ""),
        configuration_notes=f"Multi-region benchmark: {', '.join(args.regions)}"
    )
    
    # Try to open dashboard in browser
    try:
        import webbrowser
        webbrowser.open(f"file://{dashboard_file}")
        print("🌐 Dashboard opened in browser!")
    except:
        print("   (Open the HTML file in your browser to view)")
    
    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    main()

