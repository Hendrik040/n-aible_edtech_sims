"""
Daytona Parallel Sandbox Capacity Test
=======================================
Integration test that spins up N sandboxes in parallel to probe Daytona tier limits,
measure creation latency, and validate basic code execution across all sandboxes.

REQUIREMENTS:
  - DAYTONA_API_KEY env var (or .env file loaded by pytest)
  - Real Daytona account (skipped automatically when key is absent)

TIER CONTEXT (as of 2026-03):
  Tier | vCPU | RAM (GiB) | Note
  -----|------|-----------|--------------------------------
    1  |  10  |    10     | Email-verified only
    2  | 100  |   200     | Credit card + $25 top-up
    3  | 250  |   500     | Higher tier
    4  | 500  | 1 000     | Enterprise baseline
  Custom region: no hard limits (invite-only, contact support)

  Default sandbox size: 1 vCPU / 1 GiB RAM / 3 GiB disk
  Cost: ~$0.067/h per sandbox (1 vCPU + 1 GiB)

SCALING MATH for default (1 vCPU / 1 GiB) sandboxes:
  SANDBOX_COUNT | vCPU needed | Minimum tier
  -------------|-------------|-------------
       10       |     10      | Tier 1 (edge)
       50       |     50      | Tier 2
      100       |    100      | Tier 2 (max)
      150       |    150      | Tier 3 needed  ← expected failure on Tier 2
      250       |    250      | Tier 3 (max)

USAGE:
  # Safe smoke test (10 sandboxes)
  pytest tests/sandbox_scaling/test_parallel_sandbox_capacity.py -v -s

  # Full tier-2 stress test — likely hits limits!
  SANDBOX_COUNT=150 pytest tests/sandbox_scaling/test_parallel_sandbox_capacity.py -v -s

  # Tune sandbox sizing (to fit more under the vCPU cap)
  SANDBOX_COUNT=50 pytest tests/sandbox_scaling/test_parallel_sandbox_capacity.py -v -s

  # Override batch size (avoid hitting the 400 creates/min rate limit)
  SANDBOX_COUNT=150 BATCH_SIZE=50 BATCH_DELAY_S=5 \\
    pytest tests/sandbox_scaling/test_parallel_sandbox_capacity.py -v -s
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import List, Optional

import pytest
import pytest_asyncio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (all overridable via env vars)
# ---------------------------------------------------------------------------

# How many sandboxes to spin up in parallel
SANDBOX_COUNT = int(os.environ.get("SANDBOX_COUNT", "10"))

# Max concurrent creates per batch — keeps us under the 400 creates/min rate limit.
# 400 creates/min = ~6.6/s. A batch of 50 with a 5 s gap is well within limits.
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "50"))
BATCH_DELAY_S = float(os.environ.get("BATCH_DELAY_S", "2.0"))

# Seconds to wait for a single sandbox to be ready (Daytona SDK timeout)
SANDBOX_CREATE_TIMEOUT_S = int(os.environ.get("SANDBOX_CREATE_TIMEOUT_S", "120"))

# How long to keep sandboxes alive after canary code runs before tearing down.
# Set e.g. HOLD_SECONDS=300 to observe all sandboxes in the Daytona dashboard.
HOLD_SECONDS = int(os.environ.get("HOLD_SECONDS", "0"))

# Simple canary code executed in every sandbox to verify it's actually working
CANARY_CODE = """
import sys
import os
result = 2 ** 10
print(f"sandbox={os.environ.get('HOSTNAME', 'unknown')} result={result}")
"""

DAYTONA_API_KEY = os.environ.get("DAYTONA_API_KEY", "")
DAYTONA_API_URL = os.environ.get("DAYTONA_API_URL", "")
DAYTONA_TARGET = os.environ.get("DAYTONA_TARGET", "")


# ---------------------------------------------------------------------------
# Data classes for results tracking
# ---------------------------------------------------------------------------

@dataclass
class SandboxResult:
    index: int
    sandbox_id: Optional[str] = None
    create_elapsed_s: float = 0.0
    code_elapsed_s: float = 0.0
    code_output: str = ""
    create_error: Optional[str] = None
    code_error: Optional[str] = None
    deleted: bool = False


@dataclass
class ScalingReport:
    total: int = 0
    created: int = 0
    failed_create: int = 0
    code_ok: int = 0
    code_failed: int = 0
    deleted: int = 0
    total_elapsed_s: float = 0.0
    create_times: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def avg_create_s(self) -> float:
        return sum(self.create_times) / len(self.create_times) if self.create_times else 0.0

    def max_create_s(self) -> float:
        return max(self.create_times) if self.create_times else 0.0

    def min_create_s(self) -> float:
        return min(self.create_times) if self.create_times else 0.0

    def estimated_hourly_cost_usd(self) -> float:
        """Rough cost: $0.00001400/s/vCPU + $0.00000450/s/GiB, 1+1 config."""
        vcpu_cost_per_h = 0.00001400 * 3600
        mem_cost_per_h = 0.00000450 * 3600
        return self.created * (vcpu_cost_per_h + mem_cost_per_h)

    def print_report(self) -> None:
        sep = "=" * 60
        print(f"\n{sep}")
        print("  DAYTONA PARALLEL SANDBOX CAPACITY REPORT")
        print(sep)
        print(f"  Target sandbox count  : {self.total}")
        print(f"  Successfully created  : {self.created}  ({self.failed_create} failed)")
        print(f"  Canary code OK        : {self.code_ok}  ({self.code_failed} failed)")
        print(f"  Sandboxes deleted     : {self.deleted}")
        print(f"  Total wall time       : {self.total_elapsed_s:.1f}s")
        print(f"  Create time avg/min/max: "
              f"{self.avg_create_s():.1f}s / {self.min_create_s():.1f}s / {self.max_create_s():.1f}s")
        print(f"  Est. cost if running 1h: ${self.estimated_hourly_cost_usd():.2f}")
        print(f"  Est. cost for 5 min    : ${self.estimated_hourly_cost_usd() / 12:.2f}")
        print(f"  Est. cost for 15 min   : ${self.estimated_hourly_cost_usd() / 4:.2f}")
        if self.errors:
            print("\n  First errors (up to 5):")
            for e in self.errors[:5]:
                print(f"    - {e}")
        print(sep)

        # Tier advice
        needed_vcpu = self.total
        if needed_vcpu <= 10:
            tier = "Tier 1 (email-verified)"
        elif needed_vcpu <= 100:
            tier = "Tier 2 (credit card + $25 top-up)"
        elif needed_vcpu <= 250:
            tier = "Tier 3"
        elif needed_vcpu <= 500:
            tier = "Tier 4 / Enterprise"
        else:
            tier = "Custom Region (contact sales@daytona.io)"
        print(f"  Tier recommendation   : {tier}")
        print(sep + "\n")


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

def _build_daytona_client():
    """Build an AsyncDaytona client from env config."""
    from daytona_sdk import AsyncDaytona, DaytonaConfig
    kwargs = {"api_key": DAYTONA_API_KEY}
    if DAYTONA_API_URL:
        kwargs["api_url"] = DAYTONA_API_URL
    if DAYTONA_TARGET:
        kwargs["target"] = DAYTONA_TARGET
    return AsyncDaytona(DaytonaConfig(**kwargs))


async def _create_one(daytona, index: int) -> SandboxResult:
    """Create a single sandbox and run the canary code inside it."""
    from daytona_sdk import CreateSandboxFromImageParams, Image

    result = SandboxResult(index=index)
    t0 = time.monotonic()

    try:
        params = CreateSandboxFromImageParams(
            # Bare debian-slim with no extra pip installs — fastest cold-start,
            # tests pure scheduling / tier capacity rather than image bake time.
            # Swap to Image.debian_slim("3.12").pip_install([...]) to test with
            # the full production image.
            image=Image.debian_slim("3.12"),
            language="python",
            labels={"app": "n-aible-scale-test", "index": str(index)},
            auto_stop_interval=5,      # stop after 5 min idle (test cleanup)
            auto_archive_interval=10,  # archive quickly
            auto_delete_interval=60,   # self-destruct after 1h (safety net)
        )
        sandbox = await daytona.create(params, timeout=SANDBOX_CREATE_TIMEOUT_S)
        result.sandbox_id = sandbox.id
        result.create_elapsed_s = time.monotonic() - t0
        logger.info(f"[SCALE] [{index:03d}] created {sandbox.id} in {result.create_elapsed_s:.1f}s")

        # Canary code execution
        t1 = time.monotonic()
        try:
            code_result = await sandbox.code_interpreter.run_code(CANARY_CODE)
            result.code_elapsed_s = time.monotonic() - t1
            if code_result.error:
                result.code_error = f"{code_result.error.name}: {code_result.error.value}"
            else:
                result.code_output = (code_result.stdout or "").strip()
        except Exception as ce:
            result.code_error = str(ce)
            result.code_elapsed_s = time.monotonic() - t1

    except Exception as e:
        result.create_elapsed_s = time.monotonic() - t0
        result.create_error = str(e)
        logger.warning(f"[SCALE] [{index:03d}] creation FAILED: {e}")

    return result


async def _delete_one(daytona, sandbox_id: str, index: int) -> bool:
    try:
        sandbox = await daytona.get(sandbox_id)
        await daytona.delete(sandbox)
        logger.info(f"[SCALE] [{index:03d}] deleted {sandbox_id}")
        return True
    except Exception as e:
        logger.warning(f"[SCALE] [{index:03d}] delete failed for {sandbox_id}: {e}")
        return False


async def _run_scaling_test(count: int) -> ScalingReport:
    """
    Core test logic:
    1. Create `count` sandboxes in parallel batches (to respect rate limits)
    2. Run canary code in each successful sandbox
    3. Delete all sandboxes
    4. Return a ScalingReport
    """
    daytona = _build_daytona_client()
    report = ScalingReport(total=count)
    results: List[SandboxResult] = []

    wall_start = time.monotonic()

    # --- Phase 1: Create in batches ---
    indices = list(range(count))
    for batch_start in range(0, count, BATCH_SIZE):
        batch = indices[batch_start: batch_start + BATCH_SIZE]
        batch_label = f"batch {batch_start // BATCH_SIZE + 1} ({batch[0]}–{batch[-1]})"
        logger.info(f"[SCALE] Starting {batch_label} ({len(batch)} sandboxes)")

        batch_results = await asyncio.gather(
            *[_create_one(daytona, i) for i in batch],
            return_exceptions=False,
        )
        results.extend(batch_results)

        if batch_start + BATCH_SIZE < count:
            logger.info(f"[SCALE] Batch done, waiting {BATCH_DELAY_S}s before next batch")
            await asyncio.sleep(BATCH_DELAY_S)

    # --- Tally results ---
    for r in results:
        if r.create_error:
            report.failed_create += 1
            report.errors.append(f"[{r.index:03d}] create: {r.create_error}")
        else:
            report.created += 1
            report.create_times.append(r.create_elapsed_s)

        if r.sandbox_id:
            if r.code_error:
                report.code_failed += 1
                report.errors.append(f"[{r.index:03d}] code: {r.code_error}")
            else:
                report.code_ok += 1

    # --- Hold phase: keep sandboxes alive so they're visible in the dashboard ---
    sandbox_ids = [(r.index, r.sandbox_id) for r in results if r.sandbox_id]
    if HOLD_SECONDS > 0 and sandbox_ids:
        print(f"\n[SCALE] {len(sandbox_ids)} sandboxes are LIVE — holding for {HOLD_SECONDS}s "
              f"(check app.daytona.io now)")
        for remaining in range(HOLD_SECONDS, 0, -10):
            print(f"[SCALE]   tearing down in {remaining}s ...", flush=True)
            await asyncio.sleep(min(10, remaining))
        print("[SCALE] Hold complete — starting teardown\n")

    # --- Phase 2: Delete all created sandboxes ---
    if sandbox_ids:
        logger.info(f"[SCALE] Deleting {len(sandbox_ids)} sandboxes...")
        delete_results = await asyncio.gather(
            *[_delete_one(daytona, sid, idx) for idx, sid in sandbox_ids],
            return_exceptions=False,
        )
        report.deleted = sum(1 for ok in delete_results if ok)

    report.total_elapsed_s = time.monotonic() - wall_start
    return report


# ---------------------------------------------------------------------------
# Pytest test
# ---------------------------------------------------------------------------

pytestmark = [
    pytest.mark.integration,
    pytest.mark.sandbox_scaling,
]


@pytest.fixture(scope="module")
def daytona_available():
    """Skip the entire module if no Daytona API key is configured."""
    if not DAYTONA_API_KEY:
        pytest.skip(
            "DAYTONA_API_KEY not set — skipping live Daytona sandbox scaling test. "
            "Set DAYTONA_API_KEY (and optionally DAYTONA_API_URL / DAYTONA_TARGET) to run."
        )
    try:
        from daytona_sdk import AsyncDaytona  # noqa: F401
    except ImportError:
        pytest.skip("daytona-sdk not installed (pip install daytona-sdk)")


@pytest.mark.asyncio
async def test_parallel_sandbox_capacity(daytona_available):  # noqa: ARG001
    """
    Spin up SANDBOX_COUNT sandboxes in parallel, verify canary code runs in each,
    then tear everything down. Reports timing, success rate, and cost estimates.

    Tier 2 (100 vCPU) can support up to ~100 default (1 vCPU) sandboxes.
    Setting SANDBOX_COUNT=150 will expose the limit — expect failures if on Tier 2.
    Set SANDBOX_COUNT=10 for a quick smoke test.

    Current config:
      SANDBOX_COUNT = {count}
      BATCH_SIZE    = {batch}
      BATCH_DELAY_S = {delay}s
    """.format(count=SANDBOX_COUNT, batch=BATCH_SIZE, delay=BATCH_DELAY_S)

    print(f"\n[SCALE] Starting parallel sandbox capacity test: {SANDBOX_COUNT} sandboxes")
    print(f"[SCALE] Batch size={BATCH_SIZE}, inter-batch delay={BATCH_DELAY_S}s")
    print("[SCALE] Tier 2 can handle ~100 default sandboxes (100 vCPU limit).")
    if SANDBOX_COUNT > 100:
        print(f"[SCALE] WARNING: {SANDBOX_COUNT} > 100 — expect quota failures on Tier 2!")

    report = await _run_scaling_test(SANDBOX_COUNT)
    report.print_report()

    # --- Assertions ---
    # We expect at least 80% creation success to pass. This threshold surfaces
    # real infrastructure issues vs. transient failures. Adjust as needed.
    success_rate = report.created / report.total if report.total else 0
    assert success_rate >= 0.8, (
        f"Too many sandbox creation failures: {report.failed_create}/{report.total} failed "
        f"(success rate {success_rate:.0%} < 80%). "
        f"First errors: {report.errors[:3]}"
    )

    # All successfully created sandboxes should execute canary code
    if report.created > 0:
        code_rate = report.code_ok / report.created
        assert code_rate >= 0.9, (
            f"Too many code execution failures: {report.code_failed}/{report.created} failed "
            f"(rate {code_rate:.0%} < 90%). Errors: {report.errors[:3]}"
        )
