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
import { buildApiUrl } from "@/lib/api"

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RalphLoopData {
  prs_merged: number
  open_issues: number
  merged_prs: { number: number; title: string; merged_at: string }[]
}

interface SummaryData {
  total_traces: number
  traces_today: number
  avg_latency_ms: number
  avg_tokens: number
  agent_type_distribution: Record<string, number>
}

interface LatencyRow {
  agent_type: string
  p50: number
  p90: number
  p95: number
  p99: number
}

interface PromptVersionRow {
  version: string
  agent_type: string
  call_count: number
  avg_latency_ms: number
  avg_tokens: number
}

interface TimelineBucket {
  hour: string
  count: number
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function adminFetch<T>(path: string): Promise<T> {
  return fetch(buildApiUrl(`/api/admin/dashboard${path}`), {
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

  // Auto-refresh every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      setRefreshKey((k) => k + 1)
      setSecondsAgo(0)
    }, 30_000)
    return () => clearInterval(interval)
  }, [])

  // Tick the "last updated" counter every second
  useEffect(() => {
    const tick = setInterval(() => setSecondsAgo((s) => s + 1), 1000)
    return () => clearInterval(tick)
  }, [])

  const ralph = useSection<RalphLoopData>("/ralph-loop", refreshKey)
  const summary = useSection<SummaryData>("/summary", refreshKey)
  const latency = useSection<LatencyRow[]>("/traces/latency", refreshKey)
  const versions = useSection<PromptVersionRow[]>("/prompt-versions", refreshKey)
  const timeline = useSection<TimelineBucket[]>("/traces/timeline", refreshKey)

  const handleManualRefresh = useCallback(() => {
    setRefreshKey((k) => k + 1)
    setSecondsAgo(0)
  }, [])

  // Compute max for timeline bar height
  const maxCount = timeline.data
    ? Math.max(...timeline.data.map((b) => b.count), 1)
    : 1

  // Agent distribution bar
  const totalDist = summary.data
    ? Object.values(summary.data.agent_type_distribution).reduce((a, b) => a + b, 0)
    : 0

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
                value={ralph.data.prs_merged}
                badge={{ label: "merged", className: "bg-green-500/20 text-green-500 border-green-500/30" }}
              />
              <StatCard title="Open Issues" value={ralph.data.open_issues} />
            </div>

            {ralph.data.merged_prs.length > 0 && (
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Merged Pull Requests</CardTitle>
                </CardHeader>
                <CardContent className="max-h-64 overflow-y-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-20">PR #</TableHead>
                        <TableHead>Title</TableHead>
                        <TableHead className="w-32 text-right">Merged</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {ralph.data.merged_prs.map((pr) => (
                        <TableRow key={pr.number}>
                          <TableCell className="font-mono text-muted-foreground">#{pr.number}</TableCell>
                          <TableCell>{pr.title}</TableCell>
                          <TableCell className="text-right text-muted-foreground text-xs">
                            {formatDate(pr.merged_at)}
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
                <StatCard title="Traces Today" value={summary.data.traces_today} />
                <StatCard
                  title="Avg Latency"
                  value={`${Math.round(summary.data.avg_latency_ms)} ms`}
                />
                <StatCard
                  title="Avg Tokens"
                  value={Math.round(summary.data.avg_tokens)}
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
                      {Object.entries(summary.data.agent_type_distribution).map(
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
                      {Object.entries(summary.data.agent_type_distribution).map(
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
                    {latency.data.map((row) => (
                      <TableRow key={row.agent_type}>
                        <TableCell className="font-medium capitalize">{row.agent_type}</TableCell>
                        {([row.p50, row.p90, row.p95, row.p99] as number[]).map((v, i) => (
                          <TableCell
                            key={i}
                            className={`text-right font-mono ${latencyColor(v)}`}
                          >
                            {Math.round(v)}
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
                  {versions.data.map((row, idx) => (
                    <TableRow key={idx}>
                      <TableCell className="font-mono">{row.version}</TableCell>
                      <TableCell className="capitalize">{row.agent_type}</TableCell>
                      <TableCell className="text-right">{row.call_count}</TableCell>
                      <TableCell
                        className={`text-right font-mono ${latencyColor(row.avg_latency_ms)}`}
                      >
                        {Math.round(row.avg_latency_ms)}
                      </TableCell>
                      <TableCell className="text-right">{Math.round(row.avg_tokens)}</TableCell>
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
                {timeline.data.map((bucket, i) => {
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
                {timeline.data.map((bucket, i) => (
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
