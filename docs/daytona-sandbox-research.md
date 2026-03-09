# Daytona Sandbox Research — Handover Notes

> **Purpose:** Research summary for determining feasibility of 150 concurrent sandboxes for edtech simulation sessions (5–15 min each).
> **Date:** 2026-03-09
> **Sources:** Daytona official docs, pricing page, limits page

---

## ⚠️ Key Question

> Can we spin up **150 sandboxes simultaneously**, each running for **5–15 minutes**?

**Short answer:** Not on the default plan. Requires custom infrastructure or enterprise agreement.

---

## 1. Concurrent Sandbox Limits

From [Daytona Limits Docs](https://www.daytona.io/docs/en/limits/):

> "Organizations receive a maximum sandbox resource limit of **4 vCPUs, 8GB RAM, and 10GB disk** across all concurrent sandboxes."

> "Default sandbox configuration: **1 vCPU, 1GB RAM, 3GiB disk**"

> "**Custom infrastructure**: Organizations with custom regions have **no limits** applied for concurrent resource usage."

**Implication:** At default config (1 vCPU / 1 GB per sandbox), you can run approximately **4 concurrent sandboxes** before hitting the org-wide resource cap.

---

## 2. Platform Scale Capability

From [Daytona GitHub / ZenML blog research](https://www.zenml.io/blog/e2b-vs-daytona):

> "Daytona has demonstrated the ability to launch **10,000+ isolated instances within minutes**, showing massive parallelism potential."

**Implication:** The platform *can* support 150 concurrent sandboxes — it is gated by tier/plan, not hard technical limits.

---

## 3. Tier System

From [Daytona Limits Docs](https://www.daytona.io/docs/en/limits/):

> "Daytona uses a **4-tier system** based on verification status."

> "Organizations automatically move up tiers when they meet verification criteria, and you can manually upgrade in the Daytona Dashboard."

| Tier | Sandbox Creation Rate | Network Access |
|------|----------------------|----------------|
| Tier 1 | 300/minute | Restricted |
| Tier 2 | ~400/minute | Restricted |
| Tier 3 | ~500/minute | Full internet |
| Tier 4 | 600/minute | Full internet |

> "**Tier 1 & 2**: Restricted network access (cannot be overridden at sandbox level)"
> "**Tier 3 & 4**: Full internet access by default with custom network configuration options"

**Note:** Rate limits refer to *creation rate* (sandboxes per minute), not concurrent count. The concurrent bottleneck is the resource cap above.

---

## 4. Pricing Model

From [Daytona Pricing](https://www.daytona.io/pricing):

> "Daytona uses a **pay-as-you-go pricing model** rather than fixed plan tiers."

> "**Free credits**: $200 in compute credits at signup (no credit card required)"

> "**Startup program**: Up to $50,000 in credits available for startups"

> "Cost example: Small sandbox (1 vCPU, 1GB RAM) costs approximately **$0.067/hour** while running"

> "When sandboxes are stopped, you only pay for storage at reduced rates"

### ⚠️ Cost Calculation (Needs Verification)

The following is a *derived estimate* — **not a direct quote** — and should be verified with Daytona sales:

```
150 sandboxes × 0.25 hrs (15 min max) × $0.067/hr ≈ $2.51 per full concurrent batch
```

This calculation is based on the $0.067/hr figure from the docs. The user found this hard to believe — **confirm actual enterprise pricing with Daytona directly**, as volume/custom pricing likely differs.

---

## 5. Network Rate Limits

From [Daytona Network Limits Docs](https://www.daytona.io/docs/en/network-limits/):

> "Monitor rate limit headers: `X-RateLimit-Remaining-{throttler}`, `X-RateLimit-Reset-{throttler}`"

> "Implement exponential backoff on rate limit errors (1s, 2s, 4s, 8s delays)"

---

## 6. Gap Analysis: Our Requirement vs Default Limits

| | Our Need | Default Limit | Gap |
|---|---|---|---|
| Concurrent sandboxes | 150 | ~4 | **37x over** |
| Total vCPUs | 150 | 4 | **37x over** |
| Total RAM | 150 GB | 8 GB | **18x over** |

---

## 7. Recommended Next Steps for Research Agent

1. **Verify the $0.067/hr figure** — confirm if this applies at enterprise scale or only pay-as-you-go
2. **Clarify "custom regions"** — what is the onboarding process and minimum commitment?
3. **Ask Daytona sales** (`sales@daytona.io`) specifically:
   - Can we get 150+ concurrent sandboxes?
   - What is pricing at this scale?
   - Is there a startup/edtech discount beyond the $50K credit program?
4. **Check if startup program applies** — [Daytona Startups](https://daytonaio-ai.framer.website/startups)
5. **Evaluate alternatives** — E2B, Modal, Fly.io Machines as fallback if Daytona enterprise pricing is too high

---

## Sources

- [Limits | Daytona Docs](https://www.daytona.io/docs/en/limits/)
- [Sandbox Management | Daytona Docs](https://www.daytona.io/docs/en/sandbox-management/)
- [Network Limits | Daytona Docs](https://www.daytona.io/docs/en/network-limits/)
- [Daytona Pricing](https://www.daytona.io/pricing)
- [Daytona Startups Program](https://daytonaio-ai.framer.website/startups)
- [E2B vs Daytona — ZenML Blog](https://www.zenml.io/blog/e2b-vs-daytona)
- [Daytona GitHub](https://github.com/daytonaio/daytona)
