import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, XCircle, Loader2, Send } from 'lucide-react'
import { api } from '../lib/api'
import Ticket from '../components/Ticket'
import Badge from '../components/Badge'

function Section({ title, children }) {
  return (
    <div>
      <div className="text-[11px] font-mono uppercase tracking-wider text-faint mb-2">{title}</div>
      {children}
    </div>
  )
}

export default function ConditionsView({ onSaved }) {
  const [rawText, setRawText] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [override, setOverride] = useState(false)
  const [activeRules, setActiveRules] = useState([])

  const loadActive = () => api.activeRules().then(setActiveRules).catch(() => {})
  useEffect(() => { loadActive() }, [])

  async function handleParse() {
    if (!rawText.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    setOverride(false)
    try {
      const res = await api.parseCondition(rawText)
      setResult(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSave() {
    if (!result) return
    setSaving(true)
    try {
      await api.saveCondition(result.rule, rawText, result.strategy_key)
      setResult(null)
      setRawText('')
      setOverride(false)
      loadActive()
      onSaved?.()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  function handleDiscard() {
    setResult(null)
    setOverride(false)
  }

  const canSave =
    result &&
    result.is_valid &&
    result.ticker_check?.ok &&
    (result.issues?.length ? override : true)

  return (
    <div className="max-w-3xl">
      <h1 className="font-display text-2xl font-semibold text-text">Describe your condition</h1>
      <p className="mt-1.5 text-[13.5px] text-muted max-w-xl">
        Plain English in, a structured rule out. Every parse runs the same pipeline: schema
        check, then a deterministic conflict check, then a ticker check — all hard blocks —
        before a softer semantic review you can choose to override.
      </p>

      <div className="mt-6">
        <textarea
          value={rawText}
          onChange={(e) => setRawText(e.target.value)}
          placeholder="Buy Nifty above 25000"
          rows={3}
          className="w-full resize-none rounded-md border border-hairline bg-surface px-4 py-3 text-[14px]
                     font-mono text-text placeholder:text-faint focus:outline-none focus:border-signal-active
                     focus:ring-1 focus:ring-signal-active transition-colors"
        />
        <div className="mt-3 flex items-center gap-3">
          <button
            onClick={handleParse}
            disabled={!rawText.trim() || loading}
            className="inline-flex items-center gap-2 rounded-md bg-signal-active px-4 py-2 text-[13px] font-medium
                       text-ink hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {loading ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
            Parse &amp; validate
          </button>
          {error && (
            <span className="inline-flex items-center gap-1.5 text-[13px] text-signal-risk">
              <XCircle size={14} /> {error}
            </span>
          )}
        </div>
      </div>

      {result && (
        <div className="mt-7 space-y-5">
          <Section title="Parsed rule">
            <pre className="rounded-md border border-hairline bg-surface p-4 text-[12.5px] font-mono text-muted overflow-x-auto">
{JSON.stringify(result.rule, null, 2)}
            </pre>
          </Section>

          {result.schema_problems?.length > 0 && (
            <Ticket color="var(--color-signal-risk)" className="p-4">
              <div className="flex items-center gap-2 text-signal-risk font-medium text-[13.5px]">
                <XCircle size={16} /> Not a valid, complete trade condition
              </div>
              <ul className="mt-2 space-y-1 text-[13px] text-muted list-disc list-inside">
                {result.schema_problems.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
              <div className="mt-2 text-[12px] text-faint">
                Nothing was saved. Rephrase with a specific instrument, condition, and threshold.
              </div>
            </Ticket>
          )}

          {result.conflicts?.length > 0 && (
            <Ticket color="var(--color-signal-risk)" className="p-4">
              <div className="flex items-center gap-2 text-signal-risk font-medium text-[13.5px]">
                <XCircle size={16} /> Contradicts itself or an existing linked rule
              </div>
              <ul className="mt-2 space-y-1 text-[13px] text-muted list-disc list-inside">
                {result.conflicts.map((c, i) => <li key={i}>{c}</li>)}
              </ul>
              <div className="mt-2 text-[12px] text-faint">
                Nothing was saved. This isn't a judgment call — the logic is provably inconsistent.
              </div>
            </Ticket>
          )}

          {result.is_valid && result.ticker_check && !result.ticker_check.ok && (
            <Ticket color="var(--color-signal-risk)" className="p-4">
              <div className="flex items-center gap-2 text-signal-risk font-medium text-[13.5px]">
                <XCircle size={16} /> Ticker check failed
              </div>
              <div className="mt-1.5 text-[13px] text-muted">{result.ticker_check.message}</div>
              <div className="mt-2 text-[12px] text-faint">Nothing was saved — fix the ticker and re-parse.</div>
            </Ticket>
          )}

          {result.is_valid && result.ticker_check?.ok && (
            <>
              <div className="flex items-center gap-2 text-signal-buy text-[13.5px]">
                <CheckCircle2 size={16} />
                '{result.rule.instrument}' verified on Yahoo Finance.
              </div>

              {result.existing_version && (
                <Ticket color="var(--color-signal-wait)" className="p-4 text-[13px] text-muted">
                  This replaces your active <span className="font-mono text-text">v{result.existing_version.version}</span> rule
                  ("{result.existing_version.raw_input}") — this becomes{' '}
                  <span className="font-mono text-text">v{result.existing_version.version + 1}</span>.
                </Ticket>
              )}

              {result.issues?.length > 0 ? (
                <Ticket color="var(--color-signal-wait)" className="p-4">
                  <div className="flex items-center gap-2 text-signal-wait font-medium text-[13.5px]">
                    <AlertTriangle size={16} /> Validation agent flagged
                  </div>
                  <div className="mt-1.5 text-[13px] text-muted">{result.issues.join('; ')}</div>
                  <label className="mt-3 flex items-center gap-2 text-[13px] text-text cursor-pointer">
                    <input
                      type="checkbox"
                      checked={override}
                      onChange={(e) => setOverride(e.target.checked)}
                      className="accent-signal-active"
                    />
                    I understand the flagged issue(s) and want to save anyway
                  </label>
                </Ticket>
              ) : (
                <div className="flex items-center gap-2 text-signal-buy text-[13.5px]">
                  <CheckCircle2 size={16} /> No conflicts found against your existing active rules.
                </div>
              )}

              <div className="flex items-center gap-3 pt-1">
                <button
                  onClick={handleSave}
                  disabled={!canSave || saving}
                  className="rounded-md bg-signal-buy px-4 py-2 text-[13px] font-medium text-ink
                             hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed transition"
                >
                  {saving ? 'Saving…' : 'Confirm & save'}
                </button>
                <button
                  onClick={handleDiscard}
                  className="rounded-md border border-hairline px-4 py-2 text-[13px] font-medium text-muted
                             hover:text-text hover:border-faint transition"
                >
                  Discard
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {activeRules.length > 0 && (
        <div className="mt-10">
          <Section title={`Active rules · ${activeRules.length}`}>
            <div className="space-y-2">
              {activeRules.map((r) => (
                <Ticket key={r.rule_id} color="var(--color-signal-active)" className="p-3.5 flex items-center justify-between">
                  <div>
                    <div className="text-[13.5px] text-text font-medium">{r.instrument}</div>
                    <div className="text-[12.5px] text-faint font-mono">{r.raw_input}</div>
                  </div>
                  <Badge tone="active">v{r.version}</Badge>
                </Ticket>
              ))}
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}
