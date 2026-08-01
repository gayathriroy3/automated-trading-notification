import { useCallback, useEffect, useRef, useState } from 'react'
import { Play, Square, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import Ticket from '../components/Ticket'
import Badge from '../components/Badge'

function fmtTime(unixSeconds) {
  if (!unixSeconds) return '—'
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function railColor(status) {
  if (!status) return 'var(--color-hairline)'
  if (!status.market_open) return 'var(--color-signal-wait)'
  if (status.all_met) return 'var(--color-signal-buy)'
  return 'var(--color-signal-active)'
}

export default function MonitorView({ onMonitorChange }) {
  const [data, setData] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const timerRef = useRef(null)

  const refresh = useCallback(async () => {
    try {
      const res = await api.monitorStatus()
      setData(res)
      onMonitorChange?.(res.running)
    } catch (e) {
      setError(e.message)
    }
  }, [onMonitorChange])

  useEffect(() => {
    refresh()
    timerRef.current = setInterval(refresh, 5000)
    return () => clearInterval(timerRef.current)
  }, [refresh])

  async function handleStart() {
    setBusy(true)
    setError(null)
    try {
      await api.startMonitor()
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function handleStop() {
    setBusy(true)
    setError(null)
    try {
      await api.stopMonitor()
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const running = data?.running
  const rules = data?.rules ?? []
  const symbols = data?.symbols ?? []

  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-2xl font-semibold text-text">Live monitoring</h1>
      <p className="mt-1.5 text-[13.5px] text-muted max-w-xl">
        The gap between current market state and each active rule's conditions, recomputed
        deterministically every poll cycle. Refreshes here every 5 seconds.
      </p>

      <div className="mt-5 flex items-center gap-3">
        {data && !running && (
          rules.length > 0
            ? <span className="text-[13px] text-muted">{rules.length} active rule(s) across: {rules.map(r => r.instrument).join(', ')}</span>
            : <span className="text-[13px] text-faint">No active rules yet — add one in Conditions first.</span>
        )}
        {running && (
          <span className="text-[13px] text-muted">{rules.length} active rule(s) across: {symbols.join(', ')}</span>
        )}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={handleStart}
          disabled={running || busy || rules.length === 0}
          className="inline-flex items-center gap-2 rounded-md bg-signal-buy px-4 py-2 text-[13px] font-medium
                     text-ink hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          {busy && !running ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          Start monitoring
        </button>
        <button
          onClick={handleStop}
          disabled={!running || busy}
          className="inline-flex items-center gap-2 rounded-md border border-hairline px-4 py-2 text-[13px] font-medium
                     text-muted hover:text-signal-risk hover:border-signal-risk disabled:opacity-40 disabled:cursor-not-allowed transition"
        >
          {busy && running ? <Loader2 size={15} className="animate-spin" /> : <Square size={15} />}
          Stop monitoring
        </button>
        {error && <span className="text-[13px] text-signal-risk">{error}</span>}
      </div>

      <div className="mt-7 space-y-3">
        {!running && <div className="text-[13px] text-faint">Monitoring is stopped.</div>}

        {running && rules.length > 0 && rules.every(r => !r.status) && (
          <div className="text-[13px] text-faint">Waiting for first market update…</div>
        )}

        {running && rules.map((r) => {
          const s = r.status
          return (
            <Ticket key={r.rule_id} color={railColor(s)} className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <div className="font-display font-semibold text-[15px] text-text">{r.instrument}</div>
                  <div className="mt-0.5 text-[12px] font-mono text-faint">{r.raw_input}</div>
                </div>
                <Badge tone="muted">v{r.version}</Badge>
              </div>

              {s && (
                <>
                  <div className="mt-3 flex items-baseline gap-2">
                    <span className="text-[11px] uppercase tracking-wider text-faint font-mono">Current price</span>
                    <span className="text-[16px] font-mono text-text">{s.last_price ?? 'N/A'}</span>
                  </div>

                  <div className="mt-2">
                    {!s.market_open ? (
                      <Badge tone="wait">
                        Market closed · last {fmtTime(s.last_bar_time)}
                      </Badge>
                    ) : s.all_met ? (
                      <Badge tone="buy">Conditions satisfied</Badge>
                    ) : (
                      <div className="text-[13px] text-muted">{s.explanation ?? 'Waiting for next market update…'}</div>
                    )}
                  </div>

                  <div className="mt-2 text-[11px] font-mono text-faint">
                    last checked {fmtTime(s.updated_at)}
                  </div>
                </>
              )}
            </Ticket>
          )
        })}
      </div>
    </div>
  )
}
