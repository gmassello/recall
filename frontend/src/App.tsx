import { useState } from 'react'
import type { Ticket } from './types'
import TicketQueue from './components/TicketQueue'
import IncidentView from './components/IncidentView'
import MemoryExplorer from './components/MemoryExplorer'

type Tab = 'cola' | 'memoria'

export default function App() {
  const [tab, setTab] = useState<Tab>('cola')
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
          <button className={tab === 'cola' ? 'active' : ''} onClick={() => switchTab('cola')}>
            Cola de tickets
          </button>
          <button className={tab === 'memoria' ? 'active' : ''} onClick={() => switchTab('memoria')}>
            Memoria
          </button>
        </nav>
      </header>
      <main>
        {tab === 'memoria' ? (
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
