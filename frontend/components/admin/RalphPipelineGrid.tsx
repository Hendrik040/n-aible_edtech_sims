"use client"

// Ralph Rewrite Pipeline — per-ticket × per-phase visibility grid.
//
// Renders the data served by the backend's /api/admin/ralph-pipeline/*
// endpoints (PR-A). Uses an ASCII-art, mono-font layout with a
// stone/cream/amber palette — Claude-Code style — so the grid reads
// like a diagnostic printout rather than a chart.
//
// Three panels:
//   1. Ticket grid — one row per ticket, five circles per phase
//   2. Phase success rates — horizontal bars, same palette
//   3. Failure signatures — top clusters of (phase, detail) from last 24h
//
// Auto-refresh every 30s. SSE live drawer (expandable) shows new phase
// events as they ingest. Runs read-only against the admin API (admin
// cookie auth), never writes.

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

// ---------------------------------------------------------------------------
// Types (must match backend/modules/admin/ralph_pipeline_router.py)
// ---------------------------------------------------------------------------
interface PhaseState {
  status: "running" | "passed" | "failed" | "warn" | "skipped"
  duration_sec: number | null
  detail: string | null
  updated_at: string | null
}

interface TicketRow {
  ticket_id: string
  pr_number: number | null
  issue_number: number | null
  state: "pending" | "running" | "merged" | "failed" | "blocked"
  phases: Record<string, PhaseState | null>
  started_at: string | null
  completed_at: string | null
}

interface PhaseStat {
  phase: string
  runs: number
  passed: number
  failed: number
  warned: number
  success_rate: number
}

interface FailureSignature {
  phase: string
  detail: string
  count: number
}

interface StatsResponse {
  window_hours?: number
  phases: PhaseStat[]
  failure_signatures: FailureSignature[]
  // Supports both the original and the PR #467 follow-up field shapes.
  merged_total?: number
  open_total?: number
  merged_in_window?: number
  open_in_window?: number
  merged_all_time?: number
  open_all_time?: number
}

interface StreamEvent {
  id: number
  ticket_id: string
  iteration: number
  phase: string
  status: string
  detail: string | null
  duration_sec: number | null
  pr_number: number | null
  created_at: string
}

// ---------------------------------------------------------------------------
// Constants — phase order + palette
// ---------------------------------------------------------------------------
const GH_REPO_URL = "https://github.com/Hendrik040/n-aible_edtech_sims"
const PHASES = ["A-implement", "B-review", "C-testing", "D-merge", "E-canny"] as const
const PHASE_SHORT: Record<string, string> = {
  "A-implement": "A",
  "B-review":    "B",
  "C-testing":   "C",
  "D-merge":     "D",
  "E-canny":     "E",
}
const TOTAL_TICKETS = 22

// Earthy Claude-Code palette — mono font, stone/cream backdrops, warm
// accent colors for pass/warn/fail so the grid scans at a glance.
const statusGlyph = (status: string | undefined) => {
  switch (status) {
    case "passed":  return "●"
    case "warn":    return "⚠"
    case "failed":  return "✖"
    case "running": return "◐"
    case "skipped": return "○"
    default:        return "·"
  }
}
const statusColor = (status: string | undefined): string => {
  switch (status) {
    case "passed":  return "text-emerald-400"
    case "warn":    return "text-amber-400"
    case "failed":  return "text-rose-400"
    case "running": return "text-amber-300 animate-pulse"
    case "skipped": return "text-stone-500"
    default:        return "text-stone-600"
  }
}
const stateColor = (state: TicketRow["state"]): string => {
  switch (state) {
    case "merged":  return "text-emerald-400"
    case "running": return "text-amber-300"
    case "failed":  return "text-rose-400"
    case "pending": return "text-amber-100"
    case "blocked": return "text-stone-500"
    default:        return "text-stone-400"
  }
}

// ---------------------------------------------------------------------------
// Data hook — fetch /tickets + /stats, poll every 30s
// ---------------------------------------------------------------------------
function useRalphPipeline() {
  const [tickets, setTickets] = useState<TicketRow[]>([])
  const [stats, setStats] = useState<StatsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  // Guard against out-of-order poll responses: a slow earlier fetch
  // must not overwrite state set by a newer fetch (30s poll + network
  // jitter can produce this). Each call claims an id; only the
  // most-recent id is allowed to commit.
  const requestIdRef = useRef(0)

  const fetchPipeline = useCallback(async () => {
    const requestId = ++requestIdRef.current
    try {
      const [tRes, sRes] = await Promise.all([
        fetch("/api/proxy/api/admin/ralph-pipeline/tickets", { credentials: "include" }),
        fetch("/api/proxy/api/admin/ralph-pipeline/stats", { credentials: "include" }),
      ])
      if (!tRes.ok) throw new Error(`tickets ${tRes.status}`)
      if (!sRes.ok) throw new Error(`stats ${sRes.status}`)
      const [tData, sData] = await Promise.all([tRes.json(), sRes.json()])
      if (requestId !== requestIdRef.current) return
      setTickets(tData)
      setStats(sData)
      setError(null)
      setLastUpdated(new Date())
    } catch (e) {
      if (requestId !== requestIdRef.current) return
      setError(e instanceof Error ? e.message : "fetch failed")
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false)
      }
    }
  }, [])

  useEffect(() => {
    fetchPipeline()
    const id = setInterval(fetchPipeline, 30_000)
    return () => {
      clearInterval(id)
      // Invalidate any in-flight fetch so setState calls after unmount
      // (or after a prop-driven refetch) become no-ops.
      requestIdRef.current += 1
    }
  }, [fetchPipeline])

  return { tickets, stats, loading, error, lastUpdated, refetch: fetchPipeline }
}

// ---------------------------------------------------------------------------
// SSE hook — live phase events for the drawer
// ---------------------------------------------------------------------------
function useLiveEvents(enabled: boolean) {
  const [events, setEvents] = useState<StreamEvent[]>([])
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!enabled) {
      esRef.current?.close()
      esRef.current = null
      return
    }
    const es = new EventSource("/api/proxy/api/admin/ralph-pipeline/stream", {
      withCredentials: true,
    })
    esRef.current = es
    es.addEventListener("phase", (ev) => {
      try {
        const data: StreamEvent = JSON.parse((ev as MessageEvent).data)
        setEvents((prev) => [data, ...prev].slice(0, 50))
      } catch {
        // ignore malformed payload
      }
    })
    es.addEventListener("error", () => {
      // browser will auto-retry; nothing to do
    })
    return () => {
      es.close()
      esRef.current = null
    }
  }, [enabled])

  return events
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
interface RalphPipelineGridProps {
  // Bumped by the dashboard's header refresh button. When it changes
  // we re-fetch tickets + stats so the grid doesn't stay stale for up
  // to the 30s poll interval.
  refreshKey?: number
}

interface SelectedPhase {
  ticketId: string
  phase: string
}

export default function RalphPipelineGrid({ refreshKey = 0 }: RalphPipelineGridProps) {
  const { tickets, stats, loading, error, lastUpdated, refetch } = useRalphPipeline()
  const [liveOpen, setLiveOpen] = useState(false)
  const liveEvents = useLiveEvents(liveOpen)
  // Selected phase for the inline detail panel. Keyboard/touch users
  // reach this by focusing + activating the glyph button; mouse users
  // still get the title tooltip. Either works.
  //
  // Only the {ticketId, phase} identity is stored here — the live
  // PhaseState is always looked up from `tickets` at render time via
  // `selectedPhaseState`, so the panel stays in sync with the 30s
  // poll instead of rendering a frozen snapshot.
  const [selectedPhase, setSelectedPhase] = useState<SelectedPhase | null>(null)
  const selectedPhaseState = useMemo<PhaseState | null>(() => {
    if (!selectedPhase) return null
    return (
      tickets.find((t) => t.ticket_id === selectedPhase.ticketId)?.phases?.[
        selectedPhase.phase
      ] ?? null
    )
  }, [selectedPhase, tickets])

  // Refetch whenever the parent dashboard signals a manual refresh.
  // Skip the initial mount — useRalphPipeline already fetches once.
  const didMountRef = useRef(false)
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true
      return
    }
    refetch()
  }, [refreshKey, refetch])

  const mergedTotal =
    stats?.merged_all_time ?? stats?.merged_total ?? 0
  const openTotal =
    stats?.open_all_time ?? stats?.open_total ?? 0

  const windowHours = stats?.window_hours ?? 24

  // Sort tickets by phase number so the grid reads phase-0.1, 1.1, 1.2, …
  const sortedTickets = useMemo(() => {
    return [...tickets].sort((a, b) => a.ticket_id.localeCompare(b.ticket_id, undefined, { numeric: true }))
  }, [tickets])

  if (loading) {
    return (
      <Card className="border-stone-700 bg-stone-900 text-stone-100">
        <CardHeader>
          <CardTitle className="text-amber-100">Ralph Rewrite Pipeline</CardTitle>
          <CardDescription className="text-stone-400">
            Loading per-ticket × per-phase grid…
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-64 bg-stone-800" />
          <Skeleton className="h-4 w-80 bg-stone-800" />
          <Skeleton className="h-4 w-72 bg-stone-800" />
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="border-stone-700 bg-stone-900 text-stone-100 font-mono">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <CardTitle className="text-amber-100 flex items-center gap-3">
              <span>Ralph Rewrite Pipeline</span>
              <Badge
                variant="outline"
                className="border-amber-500/40 bg-stone-800 text-amber-200 font-mono"
                title="All-time: distinct tickets that reached D-merge passed/warn"
              >
                {mergedTotal}/{TOTAL_TICKETS} merged · all-time
              </Badge>
              {openTotal > 0 && (
                <Badge
                  variant="outline"
                  className="border-stone-600 bg-stone-800 text-stone-300 font-mono"
                  title="All-time: distinct tickets currently started/failed but not merged"
                >
                  {openTotal} in flight · all-time
                </Badge>
              )}
            </CardTitle>
            <CardDescription className="text-stone-400 mt-1">
              Per-ticket × per-phase status from the rewrite-agent-sdk track.
              Merged / in-flight badges are all-time; success rates and
              failure signatures below are scoped to the last {windowHours}h.
              {lastUpdated && (
                <span className="ml-2 text-stone-500">
                  · updated {lastUpdated.toLocaleTimeString()}
                </span>
              )}
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setLiveOpen((v) => !v)}
            className="border-stone-600 bg-stone-800 text-amber-200 hover:bg-stone-700 hover:text-amber-100"
          >
            {liveOpen ? "✕ close live log" : "▶ live log"}
          </Button>
        </div>
        {error && (
          <div className="text-rose-400 text-sm mt-2">fetch error: {error}</div>
        )}
      </CardHeader>

      <CardContent className="space-y-6">
        {/* ───────── 1. Ticket grid (ASCII-art style) ───────── */}
        <section>
          <SectionTitle>tickets</SectionTitle>
          {sortedTickets.length === 0 ? (
            <EmptyState
              hint="No phase-transition events yet. Trigger the loop (or run scripts/rewrite/backfill-events.py) to populate."
            />
          ) : (
            <pre className="text-[13px] leading-6 overflow-x-auto bg-stone-950 border border-stone-800 rounded p-3 text-stone-200">
              <div className="text-stone-500 border-b border-stone-800 pb-1 mb-1">
                {"  ticket      A   B   C   D   E    PR      state"}
              </div>
              {sortedTickets.map((t) => (
                <div key={t.ticket_id} className="flex items-center gap-0 whitespace-pre">
                  <span className="text-stone-300">{"  "}</span>
                  <span className="w-[10ch] inline-block">
                    {t.issue_number ? (
                      <a
                        href={`${GH_REPO_URL}/issues/${t.issue_number}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={`GitHub issue #${t.issue_number} — plan for ${t.ticket_id}`}
                        className="text-amber-100 hover:text-amber-300 hover:underline focus:outline-none focus:ring-1 focus:ring-amber-400 rounded-sm"
                      >
                        {t.ticket_id}
                      </a>
                    ) : (
                      <span className="text-amber-100">{t.ticket_id}</span>
                    )}
                  </span>
                  {PHASES.map((p) => {
                    const phase = t.phases?.[p]
                    const label = phase
                      ? `${p}: ${phase.status}${phase.detail ? ` — ${phase.detail}` : ""}${
                          phase.duration_sec != null ? ` (${phase.duration_sec}s)` : ""
                        }`
                      : `${p}: —`
                    const isSelected =
                      selectedPhase?.ticketId === t.ticket_id && selectedPhase?.phase === p
                    return (
                      <button
                        type="button"
                        key={p}
                        className={`${statusColor(phase?.status)} w-[4ch] inline-block text-center bg-transparent border-0 p-0 cursor-pointer focus:outline-none focus:ring-1 focus:ring-amber-400 rounded-sm ${
                          isSelected ? "ring-1 ring-amber-400" : ""
                        }`}
                        title={label}
                        aria-label={`${t.ticket_id} ${label}`}
                        aria-expanded={isSelected}
                        onClick={() =>
                          setSelectedPhase(
                            isSelected
                              ? null
                              : { ticketId: t.ticket_id, phase: p },
                          )
                        }
                      >
                        {statusGlyph(phase?.status)}
                      </button>
                    )
                  })}
                  <span className="w-[8ch] inline-block text-right">
                    {t.pr_number ? (
                      <a
                        href={`${GH_REPO_URL}/pull/${t.pr_number}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={`GitHub PR #${t.pr_number}`}
                        className="text-stone-400 hover:text-amber-200 hover:underline focus:outline-none focus:ring-1 focus:ring-amber-400 rounded-sm"
                      >
                        {`#${t.pr_number}`}
                      </a>
                    ) : (
                      <span className="text-stone-500">—</span>
                    )}
                  </span>
                  <span className="text-stone-500 mx-2">·</span>
                  <span className={`${stateColor(t.state)} w-[10ch] inline-block`}>
                    {t.state}
                  </span>
                </div>
              ))}
              <div className="text-stone-600 border-t border-stone-800 pt-1 mt-1 text-xs">
                {"  legend  ● pass   ⚠ warn (admin-merged)   ✖ fail   ◐ running   ○ skipped   · not reached"}
              </div>
            </pre>
          )}
          {selectedPhase && (
            <div
              role="region"
              aria-live="polite"
              aria-label={`Details for ${selectedPhase.ticketId} phase ${selectedPhase.phase}`}
              className="mt-2 bg-stone-950 border border-amber-500/30 rounded p-3 text-[13px] text-stone-200"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <span className="text-amber-200">{selectedPhase.ticketId}</span>
                  <span className="text-stone-500 mx-2">·</span>
                  <span className="text-stone-300">phase {selectedPhase.phase}</span>
                  <span className="text-stone-500 mx-2">·</span>
                  <span className={statusColor(selectedPhaseState?.status)}>
                    {selectedPhaseState?.status ?? "not reached"}
                  </span>
                  {selectedPhaseState?.duration_sec != null && (
                    <span className="text-stone-500 ml-2">
                      ({selectedPhaseState.duration_sec}s)
                    </span>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedPhase(null)}
                  className="text-stone-500 hover:text-stone-200 text-xs"
                  aria-label="Close phase detail"
                >
                  ✕
                </button>
              </div>
              {selectedPhaseState?.detail && (
                <div className="mt-2 text-stone-300 whitespace-pre-wrap break-words">
                  {selectedPhaseState.detail}
                </div>
              )}
              {selectedPhaseState?.updated_at && (
                <div className="mt-2 text-stone-500 text-xs">
                  updated {new Date(selectedPhaseState.updated_at).toLocaleString()}
                </div>
              )}
            </div>
          )}
        </section>

        {/* ───────── 2. Phase success-rate bars ───────── */}
        <section>
          <SectionTitle>phase success rate · last {windowHours}h</SectionTitle>
          {stats && stats.phases.some((p) => p.runs > 0) ? (
            <pre className="text-[13px] leading-6 overflow-x-auto bg-stone-950 border border-stone-800 rounded p-3 text-stone-200">
              {stats.phases.map((p) => (
                <PhaseBar key={p.phase} stat={p} />
              ))}
            </pre>
          ) : (
            <EmptyState hint="No terminal phase events in the window yet." />
          )}
        </section>

        {/* ───────── 3. Failure signatures ───────── */}
        <section>
          <SectionTitle>recent failure signatures · last {windowHours}h</SectionTitle>
          {stats && stats.failure_signatures.length > 0 ? (
            <pre className="text-[13px] leading-6 overflow-x-auto bg-stone-950 border border-stone-800 rounded p-3 text-stone-200">
              {stats.failure_signatures.map((s, i) => (
                <div key={`${s.phase}-${i}`} className="whitespace-pre">
                  <span className="text-stone-600">{`  ${(i + 1).toString().padStart(2)}.`}</span>
                  <span className="text-rose-400 ml-2">{s.phase.padEnd(12)}</span>
                  <span className="text-amber-200 ml-2">×{s.count}</span>
                  <span className="text-stone-300 ml-2">{s.detail}</span>
                </div>
              ))}
            </pre>
          ) : (
            <div className="text-stone-500 text-sm italic">
              nothing failing — clean track
            </div>
          )}
        </section>

        {/* ───────── 4. Live log drawer (SSE) ───────── */}
        {liveOpen && (
          <section>
            <SectionTitle>live events · sse stream</SectionTitle>
            <pre className="text-[12px] leading-5 overflow-x-auto overflow-y-auto max-h-64 bg-stone-950 border border-amber-900/30 rounded p-3 text-stone-200">
              {liveEvents.length === 0 ? (
                <div className="text-stone-500">
                  {"  listening… events appear here as the loop fires them."}
                </div>
              ) : (
                liveEvents.map((e) => (
                  <div key={e.id} className="whitespace-pre">
                    <span className="text-stone-500">
                      {`  ${new Date(e.created_at).toLocaleTimeString()}  `}
                    </span>
                    <span className="text-amber-100">{e.ticket_id.padEnd(12)}</span>
                    <span className="text-stone-400">{`iter${e.iteration}  `}</span>
                    <span className={statusColor(e.status)}>
                      {e.phase.padEnd(12)} {e.status}
                    </span>
                    {e.pr_number && <span className="text-stone-500 ml-1">#{e.pr_number}</span>}
                    {e.detail && (
                      <span className="text-stone-400 ml-2">
                        {"— "}
                        {e.detail.length > 80 ? `${e.detail.slice(0, 80)}…` : e.detail}
                      </span>
                    )}
                  </div>
                ))
              )}
            </pre>
          </section>
        )}
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Sub-pieces
// ---------------------------------------------------------------------------
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-xs uppercase tracking-[0.18em] text-amber-500/70 mb-2 font-mono">
      {"── "}
      {children}
      {" "}{"─".repeat(40)}
    </div>
  )
}

function EmptyState({ hint }: { hint: string }) {
  return (
    <div className="bg-stone-950 border border-stone-800 rounded p-4 text-stone-500 text-sm italic">
      {hint}
    </div>
  )
}

function PhaseBar({ stat }: { stat: PhaseStat }) {
  const totalWidth = 24
  const rate = stat.runs > 0 ? stat.success_rate : 0
  const filled = Math.round(rate * totalWidth)
  const pct = Math.round(rate * 100)
  const barColor =
    rate >= 0.9 ? "text-emerald-400" :
    rate >= 0.5 ? "text-amber-400" :
                  "text-rose-400"
  const noRuns = stat.runs === 0
  return (
    <div className="whitespace-pre">
      <span className="text-stone-300">{"  "}</span>
      <span className="text-amber-100 w-[14ch] inline-block">{stat.phase}</span>
      <span className={`${noRuns ? "text-stone-600" : barColor} inline-block`}>
        {noRuns
          ? "─".repeat(totalWidth)
          : "█".repeat(filled) + "░".repeat(totalWidth - filled)}
      </span>
      <span className={`${noRuns ? "text-stone-500" : barColor} ml-2`}>
        {noRuns ? "  no runs" : `${pct.toString().padStart(3)}%`}
      </span>
      <span className="text-stone-500 ml-2 text-xs">
        {`(${stat.passed}/${stat.runs} — ${stat.failed}✖ ${stat.warned}⚠)`}
      </span>
    </div>
  )
}
