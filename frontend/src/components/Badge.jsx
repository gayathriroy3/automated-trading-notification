const TONES = {
  active: 'text-signal-active bg-signal-active-dim/40',
  buy: 'text-signal-buy bg-signal-buy-dim/40',
  risk: 'text-signal-risk bg-signal-risk-dim/40',
  wait: 'text-signal-wait bg-signal-wait-dim/40',
  muted: 'text-muted bg-rail/60',
}

export default function Badge({ tone = 'muted', children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-mono uppercase tracking-wider ${TONES[tone]}`}
    >
      {children}
    </span>
  )
}
