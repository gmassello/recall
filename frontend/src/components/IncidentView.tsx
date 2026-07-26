import { memo, useEffect, useRef, useState } from 'react'
import { getTicket, resolveIncident, sendFeedback, streamHandle } from '../api'
import { useAsync } from '../hooks'
import type {
  EvidenceStep,
  FeedbackResponse,
  HandleResponse,
  ResolveResponse,
  Ticket,
} from '../types'

function shortJson(value: unknown, max = 400): string {
  const text = JSON.stringify(value, null, 2) ?? 'null'
  return text.length > max ? `${text.slice(0, max)}…` : text
}

const EvidenceItem = memo(function EvidenceItem({ step }: { step: EvidenceStep }) {
  return (
    <li>
      <div className="timeline-head">
        <strong>{step.tool}</strong>
        <span className={`badge via-${step.via}`}>{step.via}</span>
      </div>
      <pre>{shortJson(step.args)}</pre>
      <pre className="returned">{shortJson(step.returned)}</pre>
    </li>
  )
})

export default function IncidentView({ ticket: initial, onBack }: { ticket: Ticket; onBack: () => void }) {
  const [ticket, setTicket] = useState(initial)
  const [handling, setHandling] = useState(false)
  const [evidence, setEvidence] = useState<EvidenceStep[]>([])
  const [result, setResult] = useState<HandleResponse | null>(null)
  const { busy: resolving, error, setError, run: runAsync } = useAsync()
  const closeStream = useRef<(() => void) | null>(null)

  const [rootCause, setRootCause] = useState('')
  const [resolution, setResolution] = useState('')
  const [supersedes, setSupersedes] = useState('')
  const [resolved, setResolved] = useState<ResolveResponse | null>(null)

  const [feedback, setFeedback] = useState<FeedbackResponse | null>(null)

  useEffect(() => () => closeStream.current?.(), [])

  const refreshTicket = () => {
    getTicket(ticket.id).then(setTicket).catch(() => {})
  }

  const run = () => {
    setHandling(true)
    setError('')
    setEvidence([])
    setResult(null)
    setFeedback(null)
    closeStream.current = streamHandle(ticket.id, {
      onEvidence: (step) => setEvidence((prev) => [...prev, step]),
      onResult: (res) => {
        setResult(res)
        setHandling(false)
        refreshTicket()
      },
      onError: (message) => {
        setError(message)
        setHandling(false)
        refreshTicket()
      },
    })
  }

  const resolve = () =>
    runAsync(async () => {
      setResolved(
        await resolveIncident(ticket.id, {
          root_cause: rootCause,
          resolution,
          supersedes: supersedes.trim() || null,
        }),
      )
      refreshTicket()
    })

  const vote = (helpful: boolean) => {
    if (!result?.most_relevant_incident) return
    const incidentId = result.most_relevant_incident.id
    runAsync(
      async () => setFeedback(await sendFeedback(ticket.id, { incident_id: incidentId, helpful })),
      { silent: true },
    )
  }

  return (
    <section>
      <div className="section-header">
        <button onClick={onBack}>← Back to the queue</button>
        <button className="primary" onClick={run} disabled={handling}>
          {handling ? 'Diagnosing...' : 'Diagnose'}
        </button>
      </div>

      <div className="card">
        <h2>{ticket.title}</h2>
        <p className="muted">
          {ticket.service ?? 'no service'} · {ticket.severity ?? 'no severity'} · {ticket.status}
        </p>
        {ticket.description && <p>{ticket.description}</p>}
      </div>

      {error && <p className="error">{error}</p>}

      {(handling || evidence.length > 0 || result) && (
        <div className="card">
          <h3>Evidence</h3>
          {evidence.length === 0 ? (
            <p className="empty">
              {handling ? 'The agent is querying memory...' : 'The agent used no tools.'}
            </p>
          ) : (
            <ol className="timeline">
              {evidence.map((step, idx) => (
                <EvidenceItem key={idx} step={step} />
              ))}
            </ol>
          )}
          {handling && evidence.length > 0 && <p className="empty">The agent is still working...</p>}
        </div>
      )}

      {result && (
        <>
          <div className="card">
            <h3>Diagnosis</h3>
            <p>
              <strong>Root cause:</strong> {result.diagnosis.root_cause}
            </p>
            {result.diagnosis.mitigation_steps.length > 0 && (
              <>
                <strong>Mitigation:</strong>
                <ul>
                  {result.diagnosis.mitigation_steps.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ul>
              </>
            )}
            <p>
              <strong>Confidence:</strong> {(result.diagnosis.confidence * 100).toFixed(0)}%
            </p>
            <div className="confidence-bar">
              <div style={{ width: `${result.diagnosis.confidence * 100}%` }} />
            </div>
          </div>

          {result.most_relevant_incident && (
            <div className="card">
              <h3>Most relevant incident</h3>
              <p>
                {result.most_relevant_incident.title}{' '}
                <span className="muted">(score {result.most_relevant_incident.score.toFixed(3)})</span>
              </p>
              <div className="actions">
                <button onClick={() => vote(true)} disabled={!!feedback}>
                  👍 It helped
                </button>
                <button onClick={() => vote(false)} disabled={!!feedback}>
                  👎 Not useful
                </button>
              </div>
              {feedback && (
                <p className="muted">
                  Feedback recorded: quality {feedback.quality_score.toFixed(2)} · {feedback.times_helpful}{' '}
                  helpful votes
                </p>
              )}
            </div>
          )}
        </>
      )}

      <div className="card">
        <h3>Resolve incident</h3>
        {resolved ? (
          <p>
            Postmortem saved as <code>{resolved.incident_id}</code>
            {resolved.superseded && (
              <>
                {' '}· supersedes <code>{resolved.superseded}</code>
              </>
            )}
          </p>
        ) : (
          <div className="form">
            <label>
              Root cause
              <textarea value={rootCause} onChange={(e) => setRootCause(e.target.value)} rows={2} />
            </label>
            <label>
              Resolution
              <textarea value={resolution} onChange={(e) => setResolution(e.target.value)} rows={2} />
            </label>
            <label>
              Supersedes (incident id, optional)
              <input value={supersedes} onChange={(e) => setSupersedes(e.target.value)} />
            </label>
            <button
              className="primary"
              onClick={resolve}
              disabled={resolving || !rootCause.trim() || !resolution.trim()}
            >
              {resolving ? 'Saving...' : 'Resolve and write postmortem'}
            </button>
          </div>
        )}
      </div>
    </section>
  )
}
