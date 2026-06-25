import { useState, useEffect, useRef, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Badge } from "@/components/ui/badge"
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import { QrCode, LogIn, LogOut, RefreshCw, Square } from "lucide-react"

const API_BASE = "http://127.0.0.1:9000/api"

type Stats = Record<string, number>

export function FetchPage() {
  const [loggedIn, setLoggedIn] = useState(false)
  const [uid, setUid] = useState("")
  const [fetching, setFetching] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressText, setProgressText] = useState("")
  const [stats, setStats] = useState<Stats>({})

  // QR dialog state
  const [qrOpen, setQrOpen] = useState(false)
  const [qrImage, setQrImage] = useState("")
  const [qrStatus, setQrStatus] = useState("")
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrKeyRef = useRef("")

  useEffect(() => {
    checkStatus()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const checkStatus = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/status`)
      if (r.ok) {
        const data = await r.json()
        setLoggedIn(data.logged_in)
        if (data.uid) setUid(data.uid)
        if (data.stats) setStats(data.stats)
      }
    } catch {
      setLoggedIn(false)
    }
  }, [])

  const startLogin = async () => {
    try {
      const r = await fetch(`${API_BASE}/login/qrcode`, { method: "POST" })
      if (!r.ok) throw new Error("QR生成失败")
      const blob = await r.blob()
      const url = URL.createObjectURL(blob)
      const key = r.headers.get("X-Qrcode-Key") || ""
      setQrImage(url)
      qrKeyRef.current = key
      setQrStatus("请使用哔哩哔哩APP扫码")
      setQrOpen(true)

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const curKey = qrKeyRef.current
          const pr = await fetch(`${API_BASE}/login/poll/${curKey}`, { method: "POST" })
          const data = await pr.json()
          switch (data.status) {
            case "success":
              clearInterval(pollRef.current!)
              setQrStatus("登录成功!")
              setLoggedIn(true)
              if (data.uid) setUid(data.uid)
              setTimeout(() => { setQrOpen(false); checkStatus() }, 500)
              break
            case "scanned":
              setQrStatus("已扫码，请在手机上确认...")
              break
            case "expired":
              setQrStatus("二维码已过期")
              clearInterval(pollRef.current!)
              break
            case "error":
              setQrStatus(`错误: ${data.message || ""}`)
              clearInterval(pollRef.current!)
              break
          }
        } catch { /* poll interval */ }
      }, 2000)
    } catch (e) {
      console.error(e)
    }
  }

  const loadCachedCookie = async () => {
    try {
      const r = await fetch(`${API_BASE}/login/cookie`, { method: "POST" })
      if (r.ok) {
        const data = await r.json()
        setLoggedIn(true)
        setUid(data.uid || "")
        await checkStatus()
      }
    } catch { /* no cache */ }
  }

  const logout = async () => {
    await fetch(`${API_BASE}/login/logout`, { method: "POST" })
    setLoggedIn(false)
    setUid("")
    setStats({})
  }

  const startFetch = async () => {
    setFetching(true)
    setProgress(0)
    try {
      const r = await fetch(`${API_BASE}/follows/fetch`, { method: "POST" })
      const reader = r.body?.getReader()
      if (!reader) { setFetching(false); return }
      const decoder = new TextDecoder()
      let buf = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buf += decoder.decode(value, { stream: true })
        const lines = buf.split("\n")
        buf = lines.pop() || ""
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.progress !== undefined) setProgress(data.progress)
              if (data.text) setProgressText(data.text)
              if (data.done) {
                setFetching(false)
                setProgressText(`完成: ${data.count || "?"} 条`)
                await checkStatus()
              }
            } catch { /* parse */ }
          }
        }
      }
    } catch {
      setFetching(false)
    }
  }

  const stopFetch = async () => {
    await fetch(`${API_BASE}/follows/fetch/stop`, { method: "POST" })
  }

  const fetchSpecial = async () => {
    try {
      const r = await fetch(`${API_BASE}/follows/fetch/special`, { method: "POST" })
      const data = await r.json()
      setProgressText(`特别关注: ${data.count} 个 ⭐`)
      await checkStatus()
    } catch { /* */ }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">拉取关注</h1>

      {/* Auth Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <LogIn className="size-5" />
            登录状态
          </CardTitle>
        </CardHeader>
        <CardContent className="flex items-center gap-4">
          <Badge variant={loggedIn ? "default" : "secondary"}>
            {loggedIn ? `已登录 UID: ${uid}` : "未登录"}
          </Badge>
          <Button size="sm" onClick={startLogin} disabled={loggedIn}>
            <QrCode className="size-4 mr-2" />扫码登录
          </Button>
          <Button size="sm" variant="outline" onClick={loadCachedCookie} disabled={loggedIn}>
            加载 Cookie
          </Button>
          <Button size="sm" variant="outline" onClick={logout} disabled={!loggedIn}>
            <LogOut className="size-4 mr-2" />注销
          </Button>
        </CardContent>
      </Card>

      {/* Fetch Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <RefreshCw className="size-5" />
            拉取关注列表
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Button onClick={startFetch} disabled={!loggedIn || fetching}>
              <RefreshCw className={fetching ? "animate-spin size-4 mr-2" : "size-4 mr-2"} />
              {fetching ? "拉取中..." : "拉取全部关注"}
            </Button>
            <Button variant="secondary" onClick={fetchSpecial} disabled={!loggedIn || fetching}>
              拉取特别关注
            </Button>
            <Button variant="secondary" disabled={!fetching} onClick={stopFetch}>
              <Square className="size-4 mr-2" />停止
            </Button>
          </div>
          {fetching && (
            <div className="space-y-2">
              <Progress value={progress} />
              <p className="text-sm text-muted-foreground">{progressText}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stats Card */}
      <Card>
        <CardHeader><CardTitle>统计</CardTitle></CardHeader>
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

      {/* QR Dialog */}
      <Dialog open={qrOpen} onOpenChange={(open) => { setQrOpen(open); if (!open && pollRef.current) clearInterval(pollRef.current) }}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader><DialogTitle>扫码登录</DialogTitle></DialogHeader>
          <div className="flex flex-col items-center gap-4 py-4">
            {qrImage && <img src={qrImage} alt="QR Code" className="w-52 h-52 rounded-md border" />}
            <p className="text-sm text-muted-foreground">{qrStatus}</p>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
