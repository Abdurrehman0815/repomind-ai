import axios from 'axios'
import type {
  HealthResponse,
  Project,
  ProjectListResponse,
  FileDocument,
  ScanSummary,
  CodeSymbol,
  SymbolListResponse,
  SymbolParseResponse,
  Dependency,
  DependencyListResponse,
} from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000,
})

export const fetchHealth = async (): Promise<HealthResponse> => {
  const response = await api.get<HealthResponse>('/health')
  return response.data
}

export const fetchHealthFull = async (): Promise<HealthResponse> => {
  const response = await api.get<HealthResponse>('/health/full')
  return response.data
}

export const fetchProjects = async (): Promise<Project[]> => {
  const response = await api.get<ProjectListResponse>('/api/v1/projects')
  return response.data.projects
}

export const fetchProject = async (projectId: string): Promise<Project> => {
  const response = await api.get<Project>(`/api/v1/projects/${projectId}`)
  return response.data
}

export const createProject = async (
  path: string,
  name?: string
): Promise<Project> => {
  const response = await api.post<Project>(
    '/api/v1/projects',
    {
      path,
      name: name || undefined,
    },
    { timeout: 180000 }
  )
  return response.data
}

export const uploadProject = async (
  files: File[],
  name: string | undefined,
  onProgress?: (percent: number) => void
): Promise<Project> => {
  const form = new FormData()
  // webkitRelativePath keeps the folder structure ("my-app/src/main.py").
  files.forEach((file) => form.append('files', file, file.webkitRelativePath || file.name))
  if (name) form.append('name', name)
  const response = await api.post<Project>('/api/v1/projects/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 600000,
    onUploadProgress: (event) => {
      if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return response.data
}

export const scanProject = async (
  projectId: string
): Promise<{ project_id: string; status: string; summary: ScanSummary }> => {
  const response = await api.post(
    `/api/v1/projects/${projectId}/scan`,
    null,
    { timeout: 180000 }
  )
  return response.data
}

export const deleteProject = async (projectId: string): Promise<void> => {
  await api.delete(`/api/v1/projects/${projectId}`)
}

export interface ChatCitation {
  file_path: string
  start_line: number
  end_line: number
  symbol?: string | null
}

export interface ChatResponse {
  session_id: string
  message_id: string
  response: string
  intent: string
  citations: ChatCitation[]
}

export const sendChatMessage = async (
  projectId: string,
  sessionId: string,
  message: string,
): Promise<ChatResponse> => {
  const response = await api.post<ChatResponse>('/api/v1/chat', null, {
    params: { project_id: projectId, session_id: sessionId, message, stream: false },
    timeout: 180000,
  })
  return response.data
}

export const fetchProjectFiles = async (
  projectId: string
): Promise<FileDocument[]> => {
  const response = await api.get<{ files: FileDocument[]; total: number }>(
    `/api/v1/projects/${projectId}/files`
  )
  return response.data.files
}

export const parseProjectSymbols = async (
  projectId: string
): Promise<SymbolParseResponse> => {
  const response = await api.post<SymbolParseResponse>(
    `/api/v1/projects/${projectId}/parse`
  )
  return response.data
}

export const fetchSymbols = async (
  projectId: string,
  params?: { name?: string; kind?: string; file_id?: string }
): Promise<CodeSymbol[]> => {
  const response = await api.get<SymbolListResponse>(
    `/api/v1/projects/${projectId}/symbols`,
    { params }
  )
  return response.data.symbols
}

export const fetchSymbol = async (
  projectId: string,
  symbolId: string
): Promise<CodeSymbol> => {
  const response = await api.get<CodeSymbol>(
    `/api/v1/projects/${projectId}/symbols/${symbolId}`
  )
  return response.data
}

export const fetchProjectDependencies = async (
  projectId: string
): Promise<Dependency[]> => {
  const response = await api.get<DependencyListResponse>(
    `/api/v1/projects/${projectId}/dependencies`
  )
  return response.data.dependencies
}

export const fetchFileDependencies = async (
  projectId: string,
  fileId: string
): Promise<Dependency[]> => {
  const response = await api.get<DependencyListResponse>(
    `/api/v1/projects/${projectId}/files/${fileId}/dependencies`
  )
  return response.data.dependencies
}

export default api
