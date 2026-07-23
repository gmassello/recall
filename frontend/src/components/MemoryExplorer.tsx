import { useEffect, useState } from 'react'
import { listMemory } from '../api'
import { useAsync } from '../hooks'
import type { Incident, Vigencia } from '../types'

const VIGENCIA_BADGE: Record<Vigencia, string> = { vigente: 'ok', vencido: 'bad', superseded: 'stale' }
const DEBOUNCE_MS = 300

export default function MemoryExplorer() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [service, setService] = useState('')
  const { error, run } = useAsync()

  useEffect(() => {
    const id = setTimeout(
      () => run(async () => setIncidents(await listMemory(service.trim() || undefined))),
      service ? DEBOUNCE_MS : 0,
    )
    return () => clearTimeout(id)
  }, [service])

  return (
    <section>
      <div className="section-header">
        <h2>Memoria de incidentes</h2>
        <input
          placeholder="Filtrar por servicio..."
          value={service}
          onChange={(e) => setService(e.target.value)}
        />
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
            </tr>
          </thead>
          <tbody>
            {incidents.map((i) => {
              return (
                <tr key={i.id}>
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
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </section>
  )
}
