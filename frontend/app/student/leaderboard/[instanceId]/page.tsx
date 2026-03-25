"use client"

import { useState, useEffect } from "react"
import { useRouter, useParams } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Trophy,
  Medal,
  ArrowLeft,
  Star,
  Users,
  Crown,
} from "lucide-react"
import RoleBasedSidebar from "@/components/RoleBasedSidebar"
import { useAuth } from "@/lib/auth-context"
import { apiClient } from "@/lib/api"

interface LeaderboardEntry {
  rank: number
  display_name: string
  score: number
  completed_at: string | null
  is_current_user: boolean
}

interface LeaderboardData {
  simulation_title: string
  cohort_title: string
  total_completed: number
  entries: LeaderboardEntry[]
  current_user_rank: number | null
}

const MEDAL_COLOURS = [
  // rank 1 — gold
  {
    border: "border-yellow-400",
    bg: "bg-gradient-to-br from-yellow-50 to-amber-50",
    badge: "bg-yellow-400 text-yellow-900",
    icon: <Crown className="h-5 w-5 text-yellow-500" />,
    ring: "ring-2 ring-yellow-300",
  },
  // rank 2 — silver
  {
    border: "border-gray-400",
    bg: "bg-gradient-to-br from-gray-50 to-slate-100",
    badge: "bg-gray-400 text-gray-900",
    icon: <Medal className="h-5 w-5 text-gray-400" />,
    ring: "ring-2 ring-gray-300",
  },
  // rank 3 — bronze
  {
    border: "border-orange-400",
    bg: "bg-gradient-to-br from-orange-50 to-amber-50",
    badge: "bg-orange-400 text-orange-900",
    icon: <Medal className="h-5 w-5 text-orange-400" />,
    ring: "ring-2 ring-orange-300",
  },
]

function PodiumCard({ entry }: { entry: LeaderboardEntry }) {
  const colours = MEDAL_COLOURS[entry.rank - 1]
  const isFirst = entry.rank === 1

  return (
    <Card
      className={`card-elevated border-2 ${colours.border} ${colours.bg} ${colours.ring} ${
        entry.is_current_user ? "ring-4 ring-blue-400" : ""
      } transition-all`}
    >
      <CardContent className={`p-5 ${isFirst ? "pt-6" : ""}`}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center justify-center w-7 h-7 rounded-full text-sm font-bold ${colours.badge}`}
            >
              {entry.rank}
            </span>
            {colours.icon}
            {entry.is_current_user && (
              <span className="text-xs font-semibold text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
                You
              </span>
            )}
          </div>
          <span className={`text-2xl font-black ${isFirst ? "text-yellow-600" : "text-gray-700"}`}>
            {entry.score}%
          </span>
        </div>
        <p className="font-semibold text-gray-900 text-base truncate">{entry.display_name}</p>
        {entry.completed_at && (
          <p className="text-xs text-gray-500 mt-1">
            {new Date(entry.completed_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
            })}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function HighlightCard({ entry }: { entry: LeaderboardEntry }) {
  return (
    <Card
      className={`card-elevated border border-amber-200 bg-amber-50/60 ${
        entry.is_current_user ? "ring-2 ring-blue-400" : ""
      }`}
    >
      <CardContent className="px-5 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center w-7 h-7 rounded-full bg-amber-200 text-amber-800 text-sm font-bold">
              {entry.rank}
            </span>
            <div>
              <p className="font-semibold text-gray-900 flex items-center gap-2">
                {entry.display_name}
                {entry.is_current_user && (
                  <span className="text-xs font-semibold text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
                    You
                  </span>
                )}
              </p>
              {entry.completed_at && (
                <p className="text-xs text-gray-500">
                  {new Date(entry.completed_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                  })}
                </p>
              )}
            </div>
          </div>
          <span className="text-xl font-bold text-amber-700">{entry.score}%</span>
        </div>
      </CardContent>
    </Card>
  )
}

function ListRow({ entry }: { entry: LeaderboardEntry }) {
  return (
    <div
      className={`flex items-center justify-between px-5 py-3 rounded-xl bg-white/90 border ${
        entry.is_current_user
          ? "border-blue-300 border-l-4 border-l-blue-500"
          : "border-gray-200/60"
      } shadow-sm`}
    >
      <div className="flex items-center gap-4">
        <span className="w-7 text-center text-sm font-semibold text-gray-500">{entry.rank}</span>
        <div>
          <p className="font-medium text-gray-900 flex items-center gap-2">
            {entry.display_name}
            {entry.is_current_user && (
              <span className="text-xs font-semibold text-blue-600 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5">
                You
              </span>
            )}
          </p>
          {entry.completed_at && (
            <p className="text-xs text-gray-400">
              {new Date(entry.completed_at).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </p>
          )}
        </div>
      </div>
      <span className="text-base font-bold text-gray-800">{entry.score}%</span>
    </div>
  )
}

export default function LeaderboardPage() {
  const router = useRouter()
  const params = useParams()
  const instanceId = params.instanceId as string
  const { user, isLoading: authLoading } = useAuth()

  const [data, setData] = useState<LeaderboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!authLoading && !user) router.push("/")
    else if (!authLoading && user && user.role !== "student" && user.role !== "admin")
      router.push("/professor/dashboard")
  }, [user, authLoading, router])

  useEffect(() => {
    if (!instanceId || !user) return
    const fetch = async () => {
      try {
        setLoading(true)
        const result = await apiClient.getSimulationLeaderboard(instanceId)
        setData(result)
      } catch {
        setError("Could not load leaderboard. Try again later.")
      } finally {
        setLoading(false)
      }
    }
    fetch()
  }, [instanceId, user])

  if (authLoading || (!user && !authLoading)) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-black" />
      </div>
    )
  }

  const podium = data?.entries.filter((e) => e.rank <= 3) ?? []
  const highlighted = data?.entries.filter((e) => e.rank >= 4 && e.rank <= 5) ?? []
  const rest = data?.entries.filter((e) => e.rank > 5) ?? []

  const outsideTop20 =
    data && data.current_user_rank !== null && data.current_user_rank > 20

  return (
    <div className="min-h-screen bg-atmospheric relative pattern-dots">
      <RoleBasedSidebar currentPath="/student/simulations" />

      <div className="ml-20 relative">
        <div className="p-8 animate-page-enter max-w-2xl mx-auto">
          {/* Back button */}
          <button
            onClick={() => router.push("/student/simulations")}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-800 mb-8 transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Simulations
          </button>

          {/* Header */}
          <div className="mb-8 stagger-1 animate-fade-scale">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-gradient-to-br from-yellow-400 to-amber-500 rounded-xl flex items-center justify-center shadow-md">
                <Trophy className="h-5 w-5 text-white" />
              </div>
              <div>
                <h1 className="text-3xl font-bold text-black tracking-tight">Leaderboard</h1>
              </div>
            </div>
            {data && (
              <div className="mt-3 pl-1">
                <p className="text-gray-800 font-semibold text-lg">{data.simulation_title}</p>
                <p className="text-gray-500 text-sm">{data.cohort_title}</p>
              </div>
            )}
          </div>

          {/* Stats bar */}
          {data && (
            <div className="flex items-center gap-2 mb-8 stagger-2 animate-fade-scale">
              <Users className="h-4 w-4 text-gray-400" />
              <span className="text-sm text-gray-500">
                <span className="font-semibold text-gray-700">{data.total_completed}</span> student
                {data.total_completed !== 1 ? "s" : ""} completed · showing top{" "}
                {data.entries.length}
              </span>
            </div>
          )}

          {loading && (
            <div className="text-center py-16">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-black mx-auto mb-4" />
              <p className="text-gray-500">Loading leaderboard…</p>
            </div>
          )}

          {error && (
            <div className="text-center py-16 text-gray-500">
              <Trophy className="h-12 w-12 mx-auto mb-4 text-gray-300" />
              <p>{error}</p>
              <Button variant="outline" className="mt-4" onClick={() => router.push("/student/simulations")}>
                Back to Simulations
              </Button>
            </div>
          )}

          {!loading && !error && data && data.entries.length === 0 && (
            <div className="text-center py-16 text-gray-500">
              <Star className="h-12 w-12 mx-auto mb-4 text-gray-300" />
              <p className="text-lg font-medium mb-1">No scores yet</p>
              <p className="text-sm">Be the first to complete this simulation!</p>
            </div>
          )}

          {!loading && !error && data && data.entries.length > 0 && (
            <div className="space-y-8">
              {/* Podium — top 3 */}
              {podium.length > 0 && (
                <div className="stagger-3 animate-fade-scale">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                    Top performers
                  </p>
                  <div className="grid grid-cols-1 gap-3">
                    {podium.map((entry) => (
                      <PodiumCard key={entry.rank} entry={entry} />
                    ))}
                  </div>
                </div>
              )}

              {/* Ranks 4–5 */}
              {highlighted.length > 0 && (
                <div className="stagger-4 animate-fade-scale">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                    Honourable mentions
                  </p>
                  <div className="space-y-2">
                    {highlighted.map((entry) => (
                      <HighlightCard key={entry.rank} entry={entry} />
                    ))}
                  </div>
                </div>
              )}

              {/* Ranks 6–20 */}
              {rest.length > 0 && (
                <div className="stagger-5 animate-fade-scale">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-3">
                    Rankings
                  </p>
                  <div className="space-y-2">
                    {rest.map((entry) => (
                      <ListRow key={entry.rank} entry={entry} />
                    ))}
                  </div>
                </div>
              )}

              {/* Out-of-top-20 footer */}
              {outsideTop20 && (
                <div className="stagger-6 animate-fade-scale border-t border-gray-200 pt-5 flex items-center justify-between px-1">
                  <span className="text-sm text-gray-500">Your position</span>
                  <span className="text-sm font-semibold text-gray-700">
                    #{data.current_user_rank} of {data.total_completed}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
