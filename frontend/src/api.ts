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
  TicketCreate,
  TicketFilters,
  TicketUpdate,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/api'
const API_KEY = import.meta.env.VITE_DEMO_API_KEY ?? ''

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = API_KEY ? { ...init?.headers, 'X-API-Key': API_KEY } : init?.headers
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.detail) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      /* response without JSON */
    }
    throw new ApiError(detail, res.status)
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

export function listTickets(filters: TicketFilters): Promise<Ticket[]> {
  const params = new URLSearchParams()
  if (filters.service) params.set('service', filters.service)
  if (filters.severity) params.set('severity', filters.severity)
  if (filters.status) params.set('status', filters.status)
  if (filters.search.trim()) params.set('search', filters.search.trim())
  if (filters.asc) params.set('order', 'asc')
  const query = params.toString()
  return request(`/tickets${query ? `?${query}` : ''}`)
}

export function getTicket(ticketId: string): Promise<Ticket> {
  return request(`/tickets/${ticketId}`)
}

export function generateTicket(): Promise<unknown> {
  return request('/tickets/generate?n=1', post())
}

export function getDiagnosis(ticketId: string): Promise<HandleResponse> {
  return request(`/tickets/${ticketId}/diagnosis`)
}

export function seedDemo(): Promise<void> {
  return request('/tickets/seed', post())
}

export function createTicket(body: TicketCreate): Promise<Ticket> {
  return request('/tickets', post(body))
}

export function updateTicket(ticketId: string, body: TicketUpdate): Promise<Ticket> {
  return request(`/tickets/${ticketId}`, send('PATCH', body))
}

export function deleteTicket(ticketId: string): Promise<void> {
  return request(`/tickets/${ticketId}`, send('DELETE'))
}

export function clearTickets(): Promise<{ deleted: number }> {
  return request('/tickets', send('DELETE'))
}

export function resolveIncident(ticketId: string, body: ResolveRequest): Promise<ResolveResponse> {
  return request(`/incidents/${ticketId}/resolve`, post(body))
}

export function sendFeedback(ticketId: string, body: FeedbackRequest): Promise<FeedbackResponse> {
  return request(`/incidents/${ticketId}/feedback`, post(body))
}

export function listMemory(service?: string): Promise<Incident[]> {
  const query = service ? `?${new URLSearchParams({ service })}` : ''
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
  const source = new EventSource(
    `${BASE}/tickets/${ticketId}/handle/stream${API_KEY ? `?key=${encodeURIComponent(API_KEY)}` : ''}`,
  )
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
    callbacks.onError('The connection with the agent was lost')
  })
  return () => source.close()
}
