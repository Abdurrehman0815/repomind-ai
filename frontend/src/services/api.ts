import axios from 'axios'
import type {
  HealthResponse,
  Project,
  ProjectListResponse,
  FileDocument,
  ScanSummary,
} from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 15000,
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
  const response = await api.post<Project>('/api/v1/projects', {
    path,
    name: name || undefined,
  })
  return response.data
}

export const scanProject = async (
  projectId: string
): Promise<{ project_id: string; status: string; summary: ScanSummary }> => {
  const response = await api.post(`/api/v1/projects/${projectId}/scan`)
  return response.data
}

export const deleteProject = async (projectId: string): Promise<void> => {
  await api.delete(`/api/v1/projects/${projectId}`)
}

export const fetchProjectFiles = async (
  projectId: string
): Promise<FileDocument[]> => {
  const response = await api.get<{ files: FileDocument[]; total: number }>(
    `/api/v1/projects/${projectId}/files`
  )
  return response.data.files
}

export default api
