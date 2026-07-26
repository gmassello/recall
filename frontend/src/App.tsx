import { useState } from 'react'
import type { Ticket } from './types'
import TicketQueue from './components/TicketQueue'
import IncidentView from './components/IncidentView'
import MemoryExplorer from './components/MemoryExplorer'

type Tab = 'queue' | 'memory'

export default function App() {
  const [tab, setTab] = useState<Tab>('queue')
  const [ticket, setTicket] = useState<Ticket | null>(null)

  const switchTab = (next: Tab) => {
    setTab(next)
    setTicket(null)
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Recall</h1>
        <nav>
          <button className={tab === 'queue' ? 'active' : ''} onClick={() => switchTab('queue')}>
            Ticket queue
          </button>
          <button className={tab === 'memory' ? 'active' : ''} onClick={() => switchTab('memory')}>
            Memory
          </button>
        </nav>
      </header>
      <main>
        {tab === 'memory' ? (
          <MemoryExplorer />
        ) : ticket ? (
          <IncidentView ticket={ticket} onBack={() => setTicket(null)} />
        ) : (
          <TicketQueue onSelect={setTicket} />
        )}
      </main>
    </div>
  )
}
