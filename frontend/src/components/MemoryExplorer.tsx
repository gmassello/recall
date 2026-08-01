import { Fragment, useEffect, useRef, useState } from 'react'
import { clearMemory, deleteIncident, listMemory, supersedeIncident, updateIncident } from '../api'
import { useAsync } from '../hooks'
import { SEVERITIES } from '../types'
import type { Incident, IncidentUpdate, Severity, Validity } from '../types'

const VALIDITY_BADGE: Record<Validity, string> = { current: 'ok', expired: 'bad', superseded: 'stale' }
const DEBOUNCE_MS = 300
const NULLABLE_FIELDS = ['service', 'root_cause', 'resolution'] as const

interface Draft {
  title: string
  symptom: string
  service: string
  severity: Severity | ''
  root_cause: string
  resolution: string
}

function draftOf(i: Incident): Draft {
  return {
    title: i.title,
    symptom: i.symptom,
    service: i.service ?? '',
    severity: SEVERITIES.find((s) => s === i.severity) ?? '',
    root_cause: i.root_cause ?? '',
    resolution: i.resolution ?? '',
  }
}

function changesOf(original: Incident, draft: Draft): IncidentUpdate {
  const changes: IncidentUpdate = {}
  if (draft.title !== original.title) changes.title = draft.title
  if (draft.symptom !== original.symptom) changes.symptom = draft.symptom
  if (draft.severity !== (original.severity ?? '')) changes.severity = draft.severity || null
  for (const field of NULLABLE_FIELDS) {
    if (draft[field] !== (original[field] ?? '')) changes[field] = draft[field] || null
  }
  return changes
}

export default function MemoryExplorer() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [service, setService] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const { busy, error, run } = useAsync()
  const seq = useRef(0)

  const reload = async () => {
    const mine = ++seq.current
    const rows = await listMemory(service.trim() || undefined)
    if (mine === seq.current) setIncidents(rows)
  }

  useEffect(() => {
    const id = setTimeout(() => run(reload), service ? DEBOUNCE_MS : 0)
    return () => clearTimeout(id)
  }, [service])

  const remove = (id: string) => {
    if (!window.confirm('Delete this incident from memory?')) return
    run(async () => {
      if (editingId === id) setEditingId(null)
      await deleteIncident(id)
      setIncidents((prev) => prev.filter((x) => x.id !== id))
    })
  }

  const wipe = () => {
    if (!window.confirm('Delete the WHOLE memory? This action cannot be undone.')) return
    run(async () => {
      setEditingId(null)
      await clearMemory()
      setIncidents([])
    })
  }

  return (
    <section>
      <div className="section-header">
        <h2>Incident memory</h2>
        <input
          aria-label="Filter by service"
          placeholder="Filter by service..."
          value={service}
          onChange={(e) => setService(e.target.value)}
        />
        <button onClick={wipe} disabled={busy || incidents.length === 0}>
          Delete all
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {incidents.length === 0 ? (
        <p className="empty">No incidents in memory.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Title</th>
              <th>Service</th>
              <th>Validity</th>
              <th>Quality</th>
              <th>Citations</th>
              <th>Helpful</th>
              <th>Root cause</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {incidents.map((i) => (
              <Fragment key={i.id}>
                <tr>
                  <td>
                    <div>{i.title}</div>
                    <div className="muted">{i.symptom}</div>
                  </td>
                  <td>{i.service ?? '—'}</td>
                  <td>
                    <span className={`badge ${VALIDITY_BADGE[i.validity]}`}>{i.validity}</span>
                  </td>
                  <td>{i.quality_score.toFixed(2)}</td>
                  <td>{i.times_cited}</td>
                  <td>{i.times_helpful}</td>
                  <td className="muted">{i.root_cause ?? '—'}</td>
                  <td>
                    <div className="actions">
                      <button
                        onClick={() => setEditingId(editingId === i.id ? null : i.id)}
                        disabled={busy}
                      >
                        {editingId === i.id ? 'Close' : 'Edit'}
                      </button>
                      <button onClick={() => remove(i.id)} disabled={busy}>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
                {editingId === i.id && (
                  <tr>
                    <td colSpan={8}>
                      <EditForm
                        incident={i}
                        others={incidents.filter((x) => x.id !== i.id)}
                        onSaved={() => {
                          setEditingId(null)
                          run(reload)
                        }}
                        onPartial={() => run(reload)}
                      />
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

interface EditFormProps {
  incident: Incident
  others: Incident[]
  onSaved: () => void
  onPartial: () => void
}

function EditForm({ incident, others, onSaved, onPartial }: EditFormProps) {
  const [draft, setDraft] = useState<Draft>(() => draftOf(incident))
  const [supersededBy, setSupersededBy] = useState('')
  const { busy, error, run } = useAsync()

  const set = (field: keyof Draft) => (value: string) =>
    setDraft((d) => ({ ...d, [field]: value }))

  const save = () =>
    run(async () => {
      const changes = changesOf(incident, draft)
      if (Object.keys(changes).length > 0) {
        await updateIncident(incident.id, changes)
      }
      if (supersededBy) {
        try {
          await supersedeIncident(incident.id, supersededBy)
        } catch (e) {
          onPartial()
          throw e
        }
      }
      onSaved()
    })

  return (
    <div className="form">
      {error && <p className="error">{error}</p>}
      <label>
        Title
        <input value={draft.title} onChange={(e) => set('title')(e.target.value)} />
      </label>
      <label>
        Symptom
        <textarea value={draft.symptom} onChange={(e) => set('symptom')(e.target.value)} rows={2} />
      </label>
      <label>
        Service
        <input value={draft.service} onChange={(e) => set('service')(e.target.value)} />
      </label>
      <label>
        Severity
        <select value={draft.severity} onChange={(e) => set('severity')(e.target.value)}>
          <option value="">—</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </label>
      <label>
        Root cause
        <textarea
          value={draft.root_cause}
          onChange={(e) => set('root_cause')(e.target.value)}
          rows={2}
        />
      </label>
      <label>
        Resolution
        <textarea
          value={draft.resolution}
          onChange={(e) => set('resolution')(e.target.value)}
          rows={2}
        />
      </label>
      <label>
        Superseded by
        <select value={supersededBy} onChange={(e) => setSupersededBy(e.target.value)}>
          <option value="">— do not supersede —</option>
          {others.map((x) => (
            <option key={x.id} value={x.id}>
              {x.title}
            </option>
          ))}
        </select>
      </label>
      <button
        className="primary"
        onClick={save}
        disabled={busy || !draft.title.trim() || !draft.symptom.trim()}
      >
        {busy ? 'Saving...' : 'Save changes'}
      </button>
    </div>
  )
}
