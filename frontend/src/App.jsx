import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { api } from './lib/api'
import Sidebar from './components/Sidebar'
import ConditionsView from './views/ConditionsView'
import MonitorView from './views/MonitorView'
import HistoryView from './views/HistoryView'

export default function App() {
  const [tab, setTab] = useState('conditions')
  const [monitorRunning, setMonitorRunning] = useState(false)
  const [configWarning, setConfigWarning] = useState(null)

  useEffect(() => {
    api.configStatus().then((res) => setConfigWarning(res.warning)).catch(() => {})
  }, [])

  const handleMonitorChange = useCallback((running) => setMonitorRunning(running), [])

  return (
    <div className="flex h-screen bg-ink">
      <Sidebar active={tab} onChange={setTab} monitorRunning={monitorRunning} />

      <div className="flex-1 overflow-y-auto">
        {configWarning && (
          <div className="flex items-start gap-2 border-b border-hairline bg-signal-wait-dim/30 px-8 py-2.5 text-[12.5px] text-signal-wait">
            <AlertTriangle size={14} className="mt-0.5 shrink-0" />
            {configWarning}
          </div>
        )}

        <main className="px-8 py-8">
          {tab === 'conditions' && <ConditionsView onSaved={() => {}} />}
          {tab === 'monitor' && <MonitorView onMonitorChange={handleMonitorChange} />}
          {tab === 'history' && <HistoryView />}
        </main>
      </div>
    </div>
  )
}
