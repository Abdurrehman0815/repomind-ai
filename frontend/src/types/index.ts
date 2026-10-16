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

export interface CodeSymbol {
  id: string
  project_id: string
  file_id: string
  name: string
  kind: string
  line_start: number
  line_end: number
  signature?: string | null
  docstring?: string | null
  parent_symbol_id?: string | null
  created_at: string
}

export interface SymbolListResponse {
  symbols: CodeSymbol[]
  total: number
}

export interface SymbolParseResponse {
  project_id: string
  status: string
  stats: {
    files_processed: number
    total_symbols: number
    symbols_by_kind: Record<string, number>
    files_with_errors: number
  }
}

export interface Dependency {
  id: string
  project_id: string
  source_file_id: string
  target_file_id?: string | null
  target_module: string
  import_statement: string
  symbol_name?: string | null
  line_number?: number | null
  created_at: string
}

export interface DependencyListResponse {
  dependencies: Dependency[]
  total: number
}
