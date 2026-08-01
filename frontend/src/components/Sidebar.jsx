import { ListChecks, Radio, History } from 'lucide-react'

const NAV = [
  { id: 'conditions', label: 'Conditions', hint: 'Write a rule', icon: ListChecks },
  { id: 'monitor', label: 'Monitor', hint: 'Watch it live', icon: Radio },
  { id: 'history', label: 'History', hint: 'Review outcomes', icon: History },
]

export default function Sidebar({ active, onChange, monitorRunning }) {
  return (
    <aside className="w-60 shrink-0 border-r border-hairline bg-surface flex flex-col">
      <div className="px-5 pt-6 pb-5 border-b border-hairline">
        <div className="font-display font-semibold text-[17px] tracking-tight text-text">
          Trade Discipline
        </div>
        <div className="mt-1 flex items-center gap-1.5 text-[11px] font-mono text-faint">
          <span
            className={`h-1.5 w-1.5 rounded-full ${monitorRunning ? 'bg-signal-buy pulse-dot' : 'bg-faint'}`}
          />
          {monitorRunning ? 'monitor running' : 'monitor idle'}
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV.map(({ id, label, hint, icon: Icon }) => {
          const isActive = active === id
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className={`w-full flex items-center gap-3 rounded-md px-3 py-2.5 text-left transition-colors cursor-pointer
                ${isActive ? 'bg-surface-raised text-text' : 'text-muted hover:text-text hover:bg-surface-raised/60'}`}
            >
              <Icon
                size={17}
                strokeWidth={2}
                className={isActive ? 'text-signal-active' : 'text-faint'}
              />
              <span className="flex flex-col">
                <span className="font-medium text-[13.5px] leading-tight">{label}</span>
                <span className="text-[11px] text-faint leading-tight">{hint}</span>
              </span>
            </button>
          )
        })}
      </nav>

      <div className="px-5 py-4 border-t border-hairline text-[11px] text-faint font-mono leading-relaxed">
        rule engine · yahoo feed
        <br />
        local build
      </div>
    </aside>
  )
}
