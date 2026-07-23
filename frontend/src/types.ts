export type Severity = 'sev1' | 'sev2' | 'sev3' | 'sev4'
export type TicketStatus = 'open' | 'handling' | 'resolved'

export interface Ticket {
  id: string
  external_id: string | null
  title: string
  description: string | null
  service: string | null
  severity: Severity | null
  status: TicketStatus
  source: string
  created_at: string
}

export type Vigencia = 'vigente' | 'vencido' | 'superseded'

export interface Incident {
  id: string
  title: string
  symptom: string
  root_cause: string | null
  resolution: string | null
  service: string | null
  severity: string | null
  created_at: string
  resolved_at: string | null
  valid_until: string | null
  superseded_by: string | null
  quality_score: number
  times_cited: number
  times_helpful: number
  source: string
  vigencia: Vigencia
}

export interface IncidentUpdate {
  title?: string
  symptom?: string
  root_cause?: string | null
  resolution?: string | null
  service?: string | null
  severity?: string | null
}

export interface Diagnosis {
  root_cause: string
  mitigation_steps: string[]
  confidence: number
}

export interface RelevantIncident {
  id: string
  title: string
  score: number
}

export interface EvidenceStep {
  tool: string
  via: string
  args: Record<string, unknown>
  returned: unknown
}

export interface HandleResponse {
  ticket_id: string
  diagnosis: Diagnosis
  most_relevant_incident: RelevantIncident | null
  evidence?: EvidenceStep[]
}

export interface ResolveRequest {
  root_cause: string
  resolution: string
  supersedes: string | null
}

export interface ResolveResponse {
  incident_id: string
  embedded: boolean
  superseded: string | null
}

export interface FeedbackRequest {
  incident_id: string
  helpful: boolean
}

export interface FeedbackResponse {
  incident_id: string
  quality_score: number
  times_helpful: number
}

