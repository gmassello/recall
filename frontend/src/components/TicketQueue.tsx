import { Fragment, useEffect, useState } from 'react'
import {
  clearTickets,
  createTicket,
  deleteTicket,
  generateTicket,
  listTickets,
  seedDemo,
  updateTicket,
} from '../api'
import { useAsync } from '../hooks'
import { SERVICES, SEVERITIES } from '../types'
import type { Severity, Ticket, TicketCreate, TicketStatus } from '../types'

const SEV_BADGE: Record<Severity, string> = { critical: 'bad', high: 'warn', medium: '', low: '' }
const STATUS_BADGE: Record<TicketStatus, string> = { open: '', handling: 'warn', resolved: 'ok' }
const NEW = 'new'
const POLL_MS = 5000

interface Draft {
  title: string
  description: string
  service: string
  severity: Severity
}

function draftOf(t?: Ticket): Draft {
  return {
    title: t?.title ?? '',
    description: t?.description ?? '',
    service: t?.service ?? '',
    severity: t?.severity ?? 'medium',
  }
}

function bodyOf(draft: Draft): TicketCreate {
  return {
    title: draft.title,
    description: draft.description || null,
    service: draft.service || null,
    severity: draft.severity,
  }
}

export default function TicketQueue({ onSelect }: { onSelect: (t: Ticket) => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [expanded, setExpanded] = useState<string | null>(null)
  const { busy, error, run } = useAsync()

  const load = async () => setTickets(await listTickets())

  const refresh = (opts?: { silent?: boolean }) => run(load, opts)

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
      await load()
    })

  const seed = () =>
    run(async () => {
      await seedDemo()
      await load()
    })

  const remove = (id: string) => {
    if (!window.confirm('Delete this ticket from the queue?')) return
    run(async () => {
      if (expanded === id) setExpanded(null)
      await deleteTicket(id)
      setTickets((prev) => prev.filter((x) => x.id !== id))
    })
  }

  const wipe = () => {
    if (!window.confirm('Delete the WHOLE queue? This action cannot be undone.')) return
    run(async () => {
      setExpanded(null)
      await clearTickets()
      setTickets([])
    })
  }

  const onSaved = () => {
    setExpanded(null)
    refresh()
  }

  const toggle = (id: string) => setExpanded(expanded === id ? null : id)

  return (
    <section>
      <div className="section-header">
        <h2>Ticket queue</h2>
        <div className="actions">
          <button onClick={() => refresh()} disabled={busy}>
            Refresh
          </button>
          <button onClick={() => toggle(NEW)} disabled={busy}>
            {expanded === NEW ? 'Cancel' : 'New ticket'}
          </button>
          <button className="primary" onClick={generate} disabled={busy}>
            {busy ? 'Generating...' : 'Generate random'}
          </button>
          <button onClick={seed} disabled={busy}>
            {busy ? 'Loading...' : 'Load examples'}
          </button>
          <button onClick={wipe} disabled={busy || tickets.length === 0}>
            Delete all
          </button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {expanded === NEW && <TicketForm onSaved={onSaved} />}
      {tickets.length === 0 ? (
        <p className="empty">No tickets. Generate one to get started.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Service</th>
              <th>Severity</th>
              <th>Status</th>
              <th>Created</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <Fragment key={t.id}>
                <tr className="clickable" onClick={() => onSelect(t)}>
                  <td>{t.title}</td>
                  <td>{t.service ?? '—'}</td>
                  <td>{t.severity && <span className={`badge ${SEV_BADGE[t.severity] ?? ''}`}>{t.severity}</span>}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[t.status]}`}>{t.status}</span>
                  </td>
                  <td>{new Date(t.created_at).toLocaleString()}</td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <div className="actions">
                      <button onClick={() => toggle(t.id)} disabled={busy}>
                        {expanded === t.id ? 'Close' : 'Edit'}
                      </button>
                      <button onClick={() => remove(t.id)} disabled={busy}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
                {expanded === t.id && (
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
  const [draft, setDraft] = useState<Draft>(() => draftOf(ticket))
  const { busy, error, run } = useAsync()

  const set = (field: keyof Draft, value: string) =>
    setDraft((d) => ({ ...d, [field]: value }))

  const save = () =>
    run(async () => {
      const body = bodyOf(draft)
      await (ticket ? updateTicket(ticket.id, body) : createTicket(body))
      onSaved()
    })

  return (
    <div className="form">
      {error && <p className="error">{error}</p>}
      <label>
        Title
        <input value={draft.title} onChange={(e) => set('title', e.target.value)} />
      </label>
      <label>
        Symptom
        <textarea
          value={draft.description}
          onChange={(e) => set('description', e.target.value)}
          rows={2}
        />
      </label>
      <label>
        Service
        <select value={draft.service} onChange={(e) => set('service', e.target.value)}>
          <option value="">(no area)</option>
          {SERVICES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label>
        Severity
        <select value={draft.severity} onChange={(e) => set('severity', e.target.value)}>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <button className="primary" onClick={save} disabled={busy || !draft.title.trim()}>
        {busy ? 'Saving...' : ticket ? 'Save changes' : 'Create ticket'}
      </button>
    </div>
  )
}
