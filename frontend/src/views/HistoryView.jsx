import { useEffect, useState } from 'react'
import { ChevronDown, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'
import { api } from '../lib/api'
import Ticket from '../components/Ticket'
import Badge from '../components/Badge'

const ACTIONS = {
  took_trade: { label: 'Took trade', tone: 'buy', icon: CheckCircle2 },
  skipped: { label: 'Skipped trade', tone: 'muted', icon: XCircle },
}

function fmtWhen(unixSeconds) {
  return new Date(unixSeconds * 1000).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function NotificationCard({ row, onSubmitted }) {
  const [expanded, setExpanded] = useState(false)
  const [pending, setPending] = useState(row.action ? row.action : 'took_trade')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  async function submit() {
    setSubmitting(true)
    setError(null)
    try {
      await api.submitAction(row.id, pending)
      onSubmitted?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Ticket color="var(--color-signal-active)" className="p-4">
      <div className="flex items-center justify-between flex-wrap gap-1.5">
        <div className="text-[13.5px] text-text font-medium">
          {row.instrument} — <span className="text-muted font-normal">{row.condition_type}</span>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-mono text-faint">
          {fmtWhen(row.triggered_at)}
          {row.rule && <Badge tone="active">v{row.rule.version}</Badge>}
        </div>
      </div>

      <div className="mt-2 text-[13.5px] text-muted leading-relaxed">{row.reason}</div>

      {row.caution && (
        <div className="mt-2 flex items-start gap-1.5 text-[12.5px] text-signal-wait">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {row.caution}
        </div>
      )}

      {row.rule && (
        <div className="mt-2.5 text-[12px] text-faint">
          Triggered by: <span className="font-mono text-muted">"{row.rule.raw_input}"</span>
        </div>
      )}

      {row.version_history?.length > 0 && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1 text-[12px] text-faint hover:text-muted transition"
          >
            <ChevronDown size={13} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
            Version history for this strategy
          </button>
          {expanded && (
            <div className="mt-1.5 space-y-1 pl-4 border-l border-hairline">
              {row.version_history.map((v, i) => (
                <div key={i} className="text-[12px] font-mono text-faint">
                  v{v.version} [{v.status}]: "{v.raw_input}"
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 pt-3 border-t border-hairline">
        {row.action ? (
          <Badge tone={ACTIONS[row.action]?.tone ?? 'muted'}>
            {ACTIONS[row.action]?.label ?? row.action}
          </Badge>
        ) : (
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-3">
              {Object.entries(ACTIONS).map(([value, { label }]) => (
                <label key={value} className="flex items-center gap-1.5 text-[13px] text-muted cursor-pointer">
                  <input
                    type="radio"
                    name={`action-${row.id}`}
                    value={value}
                    checked={pending === value}
                    onChange={() => setPending(value)}
                    className="accent-signal-active"
                  />
                  {label}
                </label>
              ))}
            </div>
            <button
              onClick={submit}
              disabled={submitting}
              className="rounded-md bg-signal-active px-3 py-1.5 text-[12.5px] font-medium text-ink
                         hover:brightness-110 disabled:opacity-40 transition"
            >
              {submitting ? 'Saving…' : 'Submit'}
            </button>
            {error && <span className="text-[12px] text-signal-risk">{error}</span>}
          </div>
        )}
      </div>
    </Ticket>
  )
}

export default function HistoryView() {
  const [rows, setRows] = useState(null)
  const [useDateFilter, setUseDateFilter] = useState(false)
  const [date, setDate] = useState('')
  const [order, setOrder] = useState('desc')
  const [error, setError] = useState(null)

  function load() {
    api.notifications(useDateFilter ? date : null, order)
      .then(setRows)
      .catch((e) => setError(e.message))
  }

  useEffect(() => { load() }, [useDateFilter, date, order])

  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-2xl font-semibold text-text">Notification history</h1>
      <p className="mt-1.5 text-[13.5px] text-muted max-w-xl">
        Every notification, with exactly which strategy version fired it.
      </p>

      <div className="mt-5 flex items-center gap-5 flex-wrap">
        <label className="flex items-center gap-2 text-[13px] text-muted cursor-pointer">
          <input
            type="checkbox"
            checked={useDateFilter}
            onChange={(e) => setUseDateFilter(e.target.checked)}
            className="accent-signal-active"
          />
          Filter by date
        </label>
        {useDateFilter && (
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-[13px] font-mono text-text
                       focus:outline-none focus:border-signal-active"
          />
        )}
        <select
          value={order}
          onChange={(e) => setOrder(e.target.value)}
          className="rounded-md border border-hairline bg-surface px-3 py-1.5 text-[13px] text-text
                     focus:outline-none focus:border-signal-active"
        >
          <option value="desc">Newest first</option>
          <option value="asc">Oldest first</option>
        </select>
      </div>

      {error && <div className="mt-4 text-[13px] text-signal-risk">{error}</div>}

      <div className="mt-6 space-y-3">
        {rows && rows.length === 0 && (
          <div className="text-[13px] text-faint">No notifications yet.</div>
        )}
        {rows?.map((row) => (
          <NotificationCard key={row.id} row={row} onSubmitted={load} />
        ))}
      </div>
    </div>
  )
}
