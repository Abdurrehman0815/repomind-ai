import axios from 'axios'
import type { HealthResponse, Project } from '@/types'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000,
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
  const response = await api.get<Project[]>('/api/v1/projects')
  return response.data
}

export default api
