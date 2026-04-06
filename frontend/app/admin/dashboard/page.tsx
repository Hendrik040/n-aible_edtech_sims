"use client"

import { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// Backend response types (must match backend/modules/admin/dashboard_router.py)

interface PRInfo {
  number: number
  title: string
  merged_at: string | null
  html_url: string | null
  linked_issue: number | null
  canny_post_id: string | null
}

const GH_REPO_URL = "https://github.com/Hendrik040/n-aible_edtech_sims"
const CANNY_URL = "https://n-aible.canny.io/admin/board/feedback/p"

interface IssueInfo {
  number: number
  title: string
  created_at: string
  labels: string[]
}

interface RalphLoopData {
  total_prs_merged: number
  prs_list: PRInfo[]
  open_issues_count: number
  issues_list: IssueInfo[]
}

interface AgentTypeCount {
  agent_type: string
  count: number
}

interface SummaryData {
  total_traces: number
  traces_last_24h: number
  avg_latency_ms: number | null
  avg_total_tokens: number | null
  by_agent_type: AgentTypeCount[]
}

interface LatencyPercentiles {
  agent_type: string
  p50: number | null
  p90: number | null
  p95: number | null
  p99: number | null
}

interface TraceLatencyResponse {
  percentiles: LatencyPercentiles[]
}

interface PromptVersionStats {
  agent_type: string
  prompt_version: string
  count: number
  avg_latency_ms: number | null
  avg_total_tokens: number | null
}

interface PromptVersionsResponse {
  versions: PromptVersionStats[]
}

interface TimelineBucket {
  hour: string
  count: number
}

interface TraceTimeline {
  buckets: TimelineBucket[]
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function adminFetch<T>(path: string): Promise<T> {
  return fetch(`/api/proxy/api/admin/dashboard${path}`, {
    credentials: "include",
  }).then((r) => {
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
    return r.json() as Promise<T>
  })
}

function latencyColor(ms: number): string {
  if (ms < 2000) return "text-green-500"
  if (ms <= 5000) return "text-amber-500"
  return "text-red-500"
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    })
  } catch {
    return iso
  }
}

// ---------------------------------------------------------------------------
// Small reusable pieces
// ---------------------------------------------------------------------------

function StatCard({
  title,
  value,
  badge,
}: {
  title: string
  value: string | number
  badge?: { label: string; className: string }
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{title}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-2">
        <span className="text-2xl font-bold">{value}</span>
        {badge && (
          <Badge className={badge.className}>{badge.label}</Badge>
        )}
      </CardContent>
    </Card>
  )
}

function SectionError({ message }: { message: string }) {
  return (
    <p className="text-sm text-red-500">
      Failed to load: {message}
    </p>
  )
}

function SectionSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section hooks (each section loads independently)
// ---------------------------------------------------------------------------

function useSection<T>(path: string, refreshKey: number) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    adminFetch<T>(path)
      .then((d) => {
        if (!cancelled) setData(d)
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [path, refreshKey])

  return { data, loading, error }
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminDashboardPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [secondsAgo, setSecondsAgo] = useState(0)

  // Auto-refresh every 3 minutes (avoid GitHub API rate limits)
  useEffect(() => {
    const interval = setInterval(() => {
      setRefreshKey((k) => k + 1)
      setSecondsAgo(0)
    }, 180_000)
    return () => clearInterval(interval)
  }, [])

  // Tick the "last updated" counter every second
  useEffect(() => {
    const tick = setInterval(() => setSecondsAgo((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [])

  const ralph = useSection<RalphLoopData>("/ralph-loop", refreshKey)
  const summary = useSection<SummaryData>("/summary", refreshKey)
  const latencyResp = useSection<TraceLatencyResponse>("/traces/latency", refreshKey)
  const versionsResp = useSection<PromptVersionsResponse>("/prompt-versions", refreshKey)
  const timelineResp = useSection<TraceTimeline>("/traces/timeline", refreshKey)

  // Unwrap nested response objects
  const latency = { ...latencyResp, data: latencyResp.data?.percentiles ?? null }
  const versions = { ...versionsResp, data: versionsResp.data?.versions ?? null }
  const timeline = { ...timelineResp, data: timelineResp.data?.buckets ?? null }

  const handleManualRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
    setSecondsAgo(0)
  }, [])

  // Compute max for timeline bar height
  const maxCount = timeline.data
    ? Math.max(...timeline.data.map((b: TimelineBucket) => b.count), 1)
    : 1

  // Agent distribution bar — convert array to totals
  const agentDistribution: Record<string, number> = {}
  if (summary.data?.by_agent_type) {
    for (const entry of summary.data.by_agent_type) {
      agentDistribution[entry.agent_type] = entry.count
    }
  }
  const totalDist = Object.values(agentDistribution).reduce((a, b) => a + b, 0)

  const distColors: Record<string, string> = {
    persona: "bg-blue-500",
    grading: "bg-amber-500",
    summarization: "bg-emerald-500",
  }

  return (
    <div className="min-h-screen bg-background text-foreground p-4 md:p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">n-aible Control Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            System health, prompt traces, and ralph loop progress
          </p>
        </div>
        <button
          onClick={handleManualRefresh}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors self-start sm:self-auto"
        >
          Last updated: {secondsAgo}s ago &middot; click to refresh
        </button>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Section A: Ralph Loop Progress                                     */}
      {/* ----------------------------------------------------------------- */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Ralph Loop Progress</h2>

        {ralph.loading ? (
          <SectionSkeleton rows={4} />
        ) : ralph.error ? (
          <SectionError message={ralph.error} />
        ) : ralph.data ? (
          <>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <StatCard
                title="PRs Merged"
                value={ralph.data.total_prs_merged}
                badge={{ label: "merged", className: "bg-green-500/20 text-green-500 border-green-500/30" }}
              />
              <StatCard title="Open Issues" value={ralph.data.open_issues_count} />
            </div>

            {ralph.data.prs_list.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Merged Pull Requests</CardTitle>
                </CardHeader>
                <CardContent className="max-h-64 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-16">PR</TableHead>
                        <TableHead>Title</TableHead>
                        <TableHead className="w-16">Issue</TableHead>
                        <TableHead className="w-16">Canny</TableHead>
                        <TableHead className="w-28 text-right">Merged</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ralph.data.prs_list.map((pr) => (
                        <TableRow key={pr.number}>
                          <TableCell className="font-mono text-sm">
                            <a
                              href={pr.html_url || `${GH_REPO_URL}/pull/${pr.number}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-500 hover:underline"
                            >
                              #{pr.number}
                            </a>
                          </TableCell>
                          <TableCell className="text-sm">{pr.title}</TableCell>
                          <TableCell className="font-mono text-sm">
                            {pr.linked_issue ? (
                              <a
                                href={`${GH_REPO_URL}/issues/${pr.linked_issue}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-500 hover:underline"
                              >
                                #{pr.linked_issue}
                              </a>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-sm">
                            {pr.canny_post_id ? (
                              <a
                                href={`${CANNY_URL}/${pr.canny_post_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-500 hover:underline"
                                title="View Canny ticket"
                              >
                                View
                              </a>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground text-xs">
                            {pr.merged_at ? formatDate(pr.merged_at) : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>
            )}
          </>
        ) : null}
      </section>

      {/* ----------------------------------------------------------------- */}
      {/* Middle row: B (Prompt Traces) + C (Latency by Agent)              */}
      {/* ----------------------------------------------------------------- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Section B: Prompt Traces Overview */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">Prompt Traces Overview</h2>

          {summary.loading ? (
            <SectionSkeleton rows={5} />
          ) : summary.error ? (
            <SectionError message={summary.error} />
          ) : summary.data ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatCard title="Total Traces" value={summary.data.total_traces} />
                <StatCard title="Traces (24h)" value={summary.data.traces_last_24h} />
                <StatCard
                  title="Avg Latency"
                  value={summary.data.avg_latency_ms != null ? `${Math.round(summary.data.avg_latency_ms)} ms` : "—"}
                />
                <StatCard
                  title="Avg Tokens"
                  value={summary.data.avg_total_tokens != null ? Math.round(summary.data.avg_total_tokens) : "—"}
                />
              </div>

              {/* Agent type distribution bar */}
              {totalDist > 0 && (
                <Card>
                  <CardHeader className="pb-2">
                    <CardDescription>Agent Type Distribution</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="flex h-5 w-full overflow-hidden rounded-full">
                      {Object.entries(agentDistribution).map(
                        ([type, count]) => (
                          <div
                            key={type}
                            className={`${distColors[type] ?? "bg-gray-500"} transition-all`}
                            style={{ width: `${(count / totalDist) * 100}%` }}
                            title={`${type}: ${count}`}
                          />
                        )
                      )}
                    </div>
                    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                      {Object.entries(agentDistribution).map(
                        ([type, count]) => (
                          <span key={type} className="flex items-center gap-1">
                            <span
                              className={`inline-block h-2.5 w-2.5 rounded-full ${distColors[type] ?? "bg-gray-500"}`}
                            />
                            {type} ({count})
                          </span>
                        )
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}
            </>
          ) : null}
        </section>

        {/* Section C: Latency by Agent */}
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">Latency by Agent</h2>

          {latency.loading ? (
            <SectionSkeleton rows={4} />
          ) : latency.error ? (
            <SectionError message={latency.error} />
          ) : latency.data && latency.data.length > 0 ? (
            <Card>
              <CardContent className="pt-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Agent Type</TableHead>
                      <TableHead className="text-right">P50</TableHead>
                      <TableHead className="text-right">P90</TableHead>
                      <TableHead className="text-right">P95</TableHead>
                      <TableHead className="text-right">P99</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {latency.data.map((row: LatencyPercentiles) => (
                      <TableRow key={row.agent_type}>
                        <TableCell className="font-medium capitalize">{row.agent_type}</TableCell>
                        {([row.p50, row.p90, row.p95, row.p99]).map((v, i) => (
                          <TableCell
                            key={i}
                            className={`text-right font-mono ${v != null ? latencyColor(v) : "text-muted-foreground"}`}
                          >
                            {v != null ? Math.round(v) : "—"}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          ) : (
            <p className="text-sm text-muted-foreground">No latency data available.</p>
          )}
        </section>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* Section D: Prompt Version Comparison                              */}
      {/* ----------------------------------------------------------------- */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Prompt Version Comparison</h2>

        {versions.loading ? (
          <SectionSkeleton rows={4} />
        ) : versions.error ? (
          <SectionError message={versions.error} />
        ) : versions.data && versions.data.length > 0 ? (
          <Card>
            <CardContent className="pt-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Version</TableHead>
                    <TableHead>Agent Type</TableHead>
                    <TableHead className="text-right">Calls</TableHead>
                    <TableHead className="text-right">Avg Latency (ms)</TableHead>
                    <TableHead className="text-right">Avg Tokens</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {versions.data.map((row: PromptVersionStats, idx: number) => (
                    <TableRow key={idx}>
                      <TableCell className="font-mono">{row.prompt_version}</TableCell>
                      <TableCell className="capitalize">{row.agent_type}</TableCell>
                      <TableCell className="text-right">{row.count}</TableCell>
                      <TableCell
                        className={`text-right font-mono ${row.avg_latency_ms != null ? latencyColor(row.avg_latency_ms) : "text-muted-foreground"}`}
                      >
                        {row.avg_latency_ms != null ? Math.round(row.avg_latency_ms) : "—"}
                      </TableCell>
                      <TableCell className="text-right">{row.avg_total_tokens != null ? Math.round(row.avg_total_tokens) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ) : (
          <p className="text-sm text-muted-foreground">No prompt version data available.</p>
        )}
      </section>

      {/* ----------------------------------------------------------------- */}
      {/* Section E: Activity Timeline                                      */}
      {/* ----------------------------------------------------------------- */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Activity Timeline (48h)</h2>

        {timeline.loading ? (
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-end gap-1 h-36">
                {Array.from({ length: 48 }).map((_, i) => (
                  <Skeleton
                    key={i}
                    className="flex-1 rounded-t"
                    style={{ height: `${15 + Math.random() * 75}%` }}
                  />
                ))}
              </div>
            </CardContent>
          </Card>
        ) : timeline.error ? (
          <SectionError message={timeline.error} />
        ) : timeline.data && timeline.data.length > 0 ? (
          <Card>
            <CardContent className="pt-4">
              {/* Bar chart */}
              <div className="flex items-end gap-[2px] h-40">
                {timeline.data.map((bucket: TimelineBucket, i: number) => {
                  const pct = maxCount > 0 ? (bucket.count / maxCount) * 100 : 0
                  return (
                    <div
                      key={i}
                      className="flex-1 group relative flex flex-col items-center"
                    >
                      {/* Tooltip on hover */}
                      <span className="absolute -top-6 hidden group-hover:block text-[10px] bg-popover text-popover-foreground border rounded px-1 py-0.5 whitespace-nowrap z-10">
                        {bucket.count} traces
                      </span>
                      <div
                        className="w-full rounded-t bg-blue-500 hover:bg-blue-400 transition-colors min-h-[2px]"
                        style={{ height: `${Math.max(pct, 1.5)}%` }}
                      />
                    </div>
                  )
                })}
              </div>
              {/* X-axis labels */}
              <div className="flex gap-[2px] mt-1">
                {timeline.data.map((bucket: TimelineBucket, i: number) => (
                  <div key={i} className="flex-1 text-center">
                    {i % 6 === 0 ? (
                      <span className="text-[9px] text-muted-foreground">
                        {bucket.hour}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        ) : (
          <p className="text-sm text-muted-foreground">No timeline data available.</p>
        )}
      </section>
    </div>
  )
}
