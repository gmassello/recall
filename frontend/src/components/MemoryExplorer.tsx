import { Fragment, useEffect, useState } from 'react'
import { clearMemory, deleteIncident, listMemory, supersedeIncident, updateIncident } from '../api'
import { useAsync } from '../hooks'
import type { Incident, IncidentUpdate, Severity, Vigencia } from '../types'

const VIGENCIA_BADGE: Record<Vigencia, string> = { vigente: 'ok', vencido: 'bad', superseded: 'stale' }
const DEBOUNCE_MS = 300
const SEVERITIES: Severity[] = ['sev1', 'sev2', 'sev3', 'sev4']
const CAMPOS_NULABLES = ['service', 'severity', 'root_cause', 'resolution'] as const

interface Draft {
  title: string
  symptom: string
  service: string
  severity: string
  root_cause: string
  resolution: string
}

function draftDe(i: Incident): Draft {
  return {
    title: i.title,
    symptom: i.symptom,
    service: i.service ?? '',
    severity: i.severity ?? '',
    root_cause: i.root_cause ?? '',
    resolution: i.resolution ?? '',
  }
}

function cambiosDe(original: Incident, draft: Draft): IncidentUpdate {
  const cambios: IncidentUpdate = {}
  if (draft.title !== original.title) cambios.title = draft.title
  if (draft.symptom !== original.symptom) cambios.symptom = draft.symptom
  for (const campo of CAMPOS_NULABLES) {
    if (draft[campo] !== (original[campo] ?? '')) cambios[campo] = draft[campo] || null
  }
  return cambios
}

export default function MemoryExplorer() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [service, setService] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const { busy, error, run } = useAsync()

  const reload = async () => setIncidents(await listMemory(service.trim() || undefined))

  useEffect(() => {
    const id = setTimeout(() => run(reload), service ? DEBOUNCE_MS : 0)
    return () => clearTimeout(id)
  }, [service])

  const remove = (id: string) => {
    if (!window.confirm('¿Eliminar este incidente de la memoria?')) return
    run(async () => {
      if (editingId === id) setEditingId(null)
      await deleteIncident(id)
      setIncidents((prev) => prev.filter((x) => x.id !== id))
    })
  }

  const wipe = () => {
    if (!window.confirm('¿Borrar TODA la memoria? Esta accion no se puede deshacer.')) return
    run(async () => {
      setEditingId(null)
      await clearMemory()
      setIncidents([])
    })
  }

  return (
    <section>
      <div className="section-header">
        <h2>Memoria de incidentes</h2>
        <input
          placeholder="Filtrar por servicio..."
          value={service}
          onChange={(e) => setService(e.target.value)}
        />
        <button onClick={wipe} disabled={busy || incidents.length === 0}>
          Borrar todo
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {incidents.length === 0 ? (
        <p className="empty">Sin incidentes en memoria.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Titulo</th>
              <th>Servicio</th>
              <th>Vigencia</th>
              <th>Calidad</th>
              <th>Citas</th>
              <th>Utiles</th>
              <th>Causa raiz</th>
              <th>Acciones</th>
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
                    <span className={`badge ${VIGENCIA_BADGE[i.vigencia]}`}>{i.vigencia}</span>
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
                        {editingId === i.id ? 'Cerrar' : 'Editar'}
                      </button>
                      <button onClick={() => remove(i.id)} disabled={busy}>
                        Eliminar
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
}

function EditForm({ incident, others, onSaved }: EditFormProps) {
  const [draft, setDraft] = useState<Draft>(() => draftDe(incident))
  const [supersededPor, setSupersededPor] = useState('')
  const { busy, error, run } = useAsync()

  const set = (campo: keyof Draft) => (value: string) =>
    setDraft((d) => ({ ...d, [campo]: value }))

  const save = () =>
    run(async () => {
      const cambios = cambiosDe(incident, draft)
      if (Object.keys(cambios).length > 0) {
        await updateIncident(incident.id, cambios)
      }
      if (supersededPor) {
        await supersedeIncident(incident.id, supersededPor)
      }
      onSaved()
    })

  return (
    <div className="form">
      {error && <p className="error">{error}</p>}
      <label>
        Titulo
        <input value={draft.title} onChange={(e) => set('title')(e.target.value)} />
      </label>
      <label>
        Sintoma
        <textarea value={draft.symptom} onChange={(e) => set('symptom')(e.target.value)} rows={2} />
      </label>
      <label>
        Servicio
        <input value={draft.service} onChange={(e) => set('service')(e.target.value)} />
      </label>
      <label>
        Severidad
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
        Causa raiz
        <textarea
          value={draft.root_cause}
          onChange={(e) => set('root_cause')(e.target.value)}
          rows={2}
        />
      </label>
      <label>
        Resolucion
        <textarea
          value={draft.resolution}
          onChange={(e) => set('resolution')(e.target.value)}
          rows={2}
        />
      </label>
      <label>
        Reemplazado por (supersede)
        <select value={supersededPor} onChange={(e) => setSupersededPor(e.target.value)}>
          <option value="">— no reemplazar —</option>
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
        {busy ? 'Guardando...' : 'Guardar cambios'}
      </button>
    </div>
  )
}
