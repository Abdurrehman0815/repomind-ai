export interface ComponentStatus {
  status: 'ok' | 'degraded' | 'unavailable' | 'unknown'
  message?: string | null
  latency_ms?: number | null
}

export interface HealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy'
  version: string
  environment: string
  uptime_seconds: number
  components: Record<string, ComponentStatus>
}

export interface Project {
  id: string
  name: string
  path: string
  status: 'unindexed' | 'indexing' | 'indexed' | 'error'
  file_count?: number
  symbol_count?: number
  chunk_count?: number
  created_at: string
  updated_at: string
}
