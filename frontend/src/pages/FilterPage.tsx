import { useState, useEffect, useRef, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Filter, Zap, Activity, Square } from "lucide-react"

const API_BASE = "http://127.0.0.1:9000/api"

export function FilterPage() {
  const [filtering, setFiltering] = useState(false)
  const [probing, setProbing] = useState(false)
  const [probeProgress, setProbeProgress] = useState({ current: 0, total: 0, running: false })
  const [stats, setStats] = useState<Record<string, number>>({})
  const probeInterval = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    checkStatus()
    return () => { if (probeInterval.current) clearInterval(probeInterval.current) }
  }, [])

  const checkStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/status`)
      if (r.ok) {
        const data = await r.json()
        if (data.stats) setStats(data.stats)
      }
    } catch { /* */ }
  }, [])

  const runFilter = async () => {
    setFiltering(true)
    try {
      const r = await fetch(`${API_BASE}/filter/run`, { method: "POST" })
      if (r.ok) {
        await r.json()
        setFiltering(false)
        await checkStatus()
      }
    } catch {
      setFiltering(false)
    }
  }

  const startProbe = async () => {
    setProbing(true)
    try {
      const r = await fetch(`${API_BASE}/filter/probe`, { method: "POST" })
      const data = await r.json()
      if (!data.running) {
        setProbing(false)
        return
      }
      // Poll progress
      probeInterval.current = setInterval(async () => {
        try {
          const pr = await fetch(`${API_BASE}/filter/progress`)
          if (pr.ok) {
            const pd = await pr.json()
            setProbeProgress(pd)
            if (!pd.running) {
              clearInterval(probeInterval.current!)
              setProbing(false)
              await checkStatus()
            }
          }
        } catch { /* */ }
      }, 1000)
    } catch {
      setProbing(false)
    }
  }

  const stopProbe = async () => {
    await fetch(`${API_BASE}/filter/probe/stop`, { method: "POST" })
  }

  const probePct = probeProgress.total > 0
    ? Math.round((probeProgress.current / probeProgress.total) * 100)
    : 0

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">规则过滤</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="size-5" />规则引擎
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Button onClick={runFilter} disabled={filtering || probing}>
              <Filter className="size-4 mr-2" />
              {filtering ? "分析中..." : "运行规则过滤"}
            </Button>
            <Button variant="secondary" onClick={startProbe} disabled={filtering || probing}>
              <Zap className={probing ? "animate-spin size-4 mr-2" : "size-4 mr-2"} />
              {probing ? "探测中..." : "深度探测"}
            </Button>
            <Button variant="secondary" disabled={!probing} onClick={stopProbe}>
              <Square className="size-4 mr-2" />停止
            </Button>
          </div>

          <Separator />

          <div className="grid grid-cols-3 gap-4">
            <div className="space-y-1">
              <div className="text-sm font-medium">保留规则</div>
              <Badge variant="outline" className="bg-green-500/10 text-green-400 border-green-500/20">11 条</Badge>
            </div>
            <div className="space-y-1">
              <div className="text-sm font-medium">删除规则</div>
              <Badge variant="outline" className="bg-red-500/10 text-red-400 border-red-500/20">10 条</Badge>
            </div>
            <div className="space-y-1">
              <div className="text-sm font-medium">探测规则</div>
              <Badge variant="outline" className="bg-orange-500/10 text-orange-400 border-orange-500/20">5 条</Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {probing && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="size-5" />探测进度
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <Progress value={probePct} />
            <p className="text-sm text-muted-foreground">
              {probeProgress.current} / {probeProgress.total} ({probePct}%)
            </p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="size-5" />状态
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-4 gap-4 text-center">
            {[
              ["总关注", stats.total_follows ?? 0],
              ["保留", stats.verdict_keep ?? 0],
              ["待删", stats.verdict_delete ?? 0],
              ["未审", stats.verdict_unreviewed ?? 0],
            ].map(([label, val]) => (
              <div key={label}>
                <div className="text-2xl font-bold">{val}</div>
                <div className="text-xs text-muted-foreground">{label}</div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
