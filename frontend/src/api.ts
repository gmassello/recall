import type {
  EvidenceStep,
  FeedbackRequest,
  FeedbackResponse,
  HandleResponse,
  Incident,
  IncidentUpdate,
  ResolveRequest,
  ResolveResponse,
  Ticket,
} from './types'

const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* respuesta sin JSON */
    }
    throw new Error(detail)
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json()
}

function send(method: string, body?: unknown): RequestInit {
  return body === undefined
    ? { method }
    : { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

function post(body?: unknown): RequestInit {
  return send('POST', body)
}

export function listTickets(): Promise<Ticket[]> {
  return request('/tickets')
}

export function getTicket(ticketId: string): Promise<Ticket> {
  return request(`/tickets/${ticketId}`)
}

export function generateTicket(): Promise<unknown> {
  return request('/tickets/generate?n=1', post())
}

export function resolveIncident(ticketId: string, body: ResolveRequest): Promise<ResolveResponse> {
  return request(`/incidents/${ticketId}/resolve`, post(body))
}

export function sendFeedback(ticketId: string, body: FeedbackRequest): Promise<FeedbackResponse> {
  return request(`/incidents/${ticketId}/feedback`, post(body))
}

export function listMemory(service?: string): Promise<Incident[]> {
  const query = service ? `?service=${encodeURIComponent(service)}` : ''
  return request(`/memory${query}`)
}

export function updateIncident(incidentId: string, body: IncidentUpdate): Promise<Incident> {
  return request(`/memory/${incidentId}`, send('PATCH', body))
}

export function deleteIncident(incidentId: string): Promise<void> {
  return request(`/memory/${incidentId}`, send('DELETE'))
}

export function clearMemory(): Promise<{ deleted: number }> {
  return request('/memory', send('DELETE'))
}

export function supersedeIncident(incidentId: string, newId: string): Promise<void> {
  return request(`/memory/${incidentId}/supersede`, send('POST', { new_id: newId }))
}

export interface StreamCallbacks {
  onEvidence: (step: EvidenceStep) => void
  onResult: (result: HandleResponse) => void
  onError: (message: string) => void
}

export function streamHandle(ticketId: string, callbacks: StreamCallbacks): () => void {
  const source = new EventSource(`${BASE}/tickets/${ticketId}/handle/stream`)
  source.addEventListener('evidence', (event) => {
    callbacks.onEvidence(JSON.parse((event as MessageEvent).data))
  })
  source.addEventListener('result', (event) => {
    source.close()
    callbacks.onResult(JSON.parse((event as MessageEvent).data))
  })
  source.addEventListener('agent_error', (event) => {
    source.close()
    callbacks.onError((event as MessageEvent).data)
  })
  source.addEventListener('error', () => {
    source.close()
    callbacks.onError('Se corto la conexion con el agente')
  })
  return () => source.close()
}
