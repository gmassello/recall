import { Fragment, useEffect, useState } from 'react'
import {
  clearTickets,
  createTicket,
  deleteTicket,
  generateTicket,
  listTickets,
  updateTicket,
} from '../api'
import { useAsync } from '../hooks'
import { SERVICES, SEVERITIES } from '../types'
import type { Severity, Ticket, TicketCreate, TicketStatus } from '../types'

const SEV_BADGE: Record<Severity, string> = { sev1: 'bad', sev2: 'warn', sev3: '', sev4: '' }
const STATUS_BADGE: Record<TicketStatus, string> = { open: '', handling: 'warn', resolved: 'ok' }
const NUEVO = 'nuevo'
const POLL_MS = 5000

interface Draft {
  title: string
  description: string
  service: string
  severity: Severity
}

function draftDe(t?: Ticket): Draft {
  return {
    title: t?.title ?? '',
    description: t?.description ?? '',
    service: t?.service ?? '',
    severity: t?.severity ?? 'sev3',
  }
}

function bodyDe(draft: Draft): TicketCreate {
  return {
    title: draft.title,
    description: draft.description || null,
    service: draft.service || null,
    severity: draft.severity,
  }
}

export default function TicketQueue({ onSelect }: { onSelect: (t: Ticket) => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [abierto, setAbierto] = useState<string | null>(null)
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

  const remove = (id: string) => {
    if (!window.confirm('¿Eliminar este ticket de la cola?')) return
    run(async () => {
      if (abierto === id) setAbierto(null)
      await deleteTicket(id)
      setTickets((prev) => prev.filter((x) => x.id !== id))
    })
  }

  const wipe = () => {
    if (!window.confirm('¿Borrar TODA la cola? Esta accion no se puede deshacer.')) return
    run(async () => {
      setAbierto(null)
      await clearTickets()
      setTickets([])
    })
  }

  const onSaved = () => {
    setAbierto(null)
    refresh()
  }

  const toggle = (id: string) => setAbierto(abierto === id ? null : id)

  return (
    <section>
      <div className="section-header">
        <h2>Cola de tickets</h2>
        <div className="actions">
          <button onClick={() => refresh()} disabled={busy}>
            Refrescar
          </button>
          <button onClick={() => toggle(NUEVO)} disabled={busy}>
            {abierto === NUEVO ? 'Cancelar' : 'Nuevo ticket'}
          </button>
          <button className="primary" onClick={generate} disabled={busy}>
            {busy ? 'Generando...' : 'Generar random'}
          </button>
          <button onClick={wipe} disabled={busy || tickets.length === 0}>
            Borrar todo
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {abierto === NUEVO && <TicketForm onSaved={onSaved} />}
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
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <Fragment key={t.id}>
                <tr className="clickable" onClick={() => onSelect(t)}>
                  <td>{t.title}</td>
                  <td>{t.service ?? '—'}</td>
                  <td>{t.severity && <span className={`badge ${SEV_BADGE[t.severity]}`}>{t.severity}</span>}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[t.status]}`}>{t.status}</span>
                  </td>
                  <td>{new Date(t.created_at).toLocaleString()}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="actions">
                      <button onClick={() => toggle(t.id)} disabled={busy}>
                        {abierto === t.id ? 'Cerrar' : 'Editar'}
                      </button>
                      <button onClick={() => remove(t.id)} disabled={busy}>
                        Eliminar
                      </button>
                    </div>
                  </td>
                </tr>
                {abierto === t.id && (
                  <tr>
                    <td colSpan={6}>
                      <TicketForm ticket={t} onSaved={onSaved} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function TicketForm({ ticket, onSaved }: { ticket?: Ticket; onSaved: () => void }) {
  const [draft, setDraft] = useState<Draft>(() => draftDe(ticket))
  const { busy, error, run } = useAsync()

  const set = (campo: keyof Draft, value: string) =>
    setDraft((d) => ({ ...d, [campo]: value }))

  const save = () =>
    run(async () => {
      const body = bodyDe(draft)
      await (ticket ? updateTicket(ticket.id, body) : createTicket(body))
      onSaved()
    })

  return (
    <div className="form">
      {error && <p className="error">{error}</p>}
      <label>
        Titulo
        <input value={draft.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      <label>
        Sintoma
        <textarea
          value={draft.description}
          onChange={(e) => set('description', e.target.value)}
          rows={2}
        />
      </label>
      <label>
        Servicio
        <select value={draft.service} onChange={(e) => set('service', e.target.value)}>
          <option value="">(sin area)</option>
          {SERVICES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label>
        Severidad
        <select value={draft.severity} onChange={(e) => set('severity', e.target.value)}>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <button className="primary" onClick={save} disabled={busy || !draft.title.trim()}>
        {busy ? 'Guardando...' : ticket ? 'Guardar cambios' : 'Crear ticket'}
      </button>
    </div>
  )
}
