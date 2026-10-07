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
  file_count: number
  total_size_bytes: number
  created_at: string
  updated_at: string
}

export interface ProjectListResponse {
  projects: Project[]
  total: number
}

export interface FileDocument {
  id: string
  project_id: string
  relative_path: string
  language: string
  size_bytes: number
  line_count: number
  ast_status: string
  file_hash: string
  created_at: string
}

export interface ScanSummary {
  project_id: string
  total_scanned: number
  added_files: number
  modified_files: number
  unchanged_files: number
  deleted_files: number
  languages: Record<string, number>
  total_size_bytes: number
  total_lines: number
}
