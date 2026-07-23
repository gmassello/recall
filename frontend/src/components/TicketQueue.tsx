import { useEffect, useState } from 'react'
import { generateTicket, listTickets } from '../api'
import { useAsync } from '../hooks'
import type { Severity, Ticket, TicketStatus } from '../types'

const SEV_BADGE: Record<Severity, string> = { sev1: 'bad', sev2: 'warn', sev3: '', sev4: '' }
const STATUS_BADGE: Record<TicketStatus, string> = { open: '', handling: 'warn', resolved: 'ok' }
const POLL_MS = 5000

export default function TicketQueue({ onSelect }: { onSelect: (t: Ticket) => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const { busy, error, run } = useAsync()

  const refresh = (opts?: { silent?: boolean }) =>
    run(async () => setTickets(await listTickets()), opts)

  useEffect(() => {
    refresh()
    const id = setInterval(() => {
      if (!document.hidden) refresh({ silent: true })
    }, POLL_MS)
    return () => clearInterval(id)
  }, [])

  const generate = () =>
    run(async () => {
      await generateTicket()
      setTickets(await listTickets())
    })

  return (
    <section>
      <div className="section-header">
        <h2>Cola de tickets</h2>
        <div className="actions">
          <button onClick={() => refresh()} disabled={busy}>
            Refrescar
          </button>
          <button className="primary" onClick={generate} disabled={busy}>
            {busy ? 'Generando...' : 'Generar ticket'}
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {tickets.length === 0 ? (
        <p className="empty">No hay tickets. Genera uno para empezar.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Titulo</th>
              <th>Servicio</th>
              <th>Severidad</th>
              <th>Estado</th>
              <th>Creado</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id} className="clickable" onClick={() => onSelect(t)}>
                <td>{t.title}</td>
                <td>{t.service ?? '—'}</td>
                <td>{t.severity && <span className={`badge ${SEV_BADGE[t.severity]}`}>{t.severity}</span>}</td>
                <td>
                  <span className={`badge ${STATUS_BADGE[t.status]}`}>{t.status}</span>
                </td>
                <td>{new Date(t.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
