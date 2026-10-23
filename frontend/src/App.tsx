import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from '@/components/layout/Layout'
import DashboardPage from '@/pages/DashboardPage'
import ProjectsPage from '@/pages/ProjectsPage'
import WorkspacePage from '@/pages/WorkspacePage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<DashboardPage />} />
          <Route path="projects" element={<ProjectsPage />} />
          <Route path="chat" element={<WorkspacePage mode="chat" />} />
          <Route path="repository" element={<WorkspacePage mode="repository" />} />
          <Route path="review" element={<WorkspacePage mode="review" />} />
          <Route path="plan" element={<WorkspacePage mode="plan" />} />
          <Route path="tests" element={<WorkspacePage mode="tests" />} />
          <Route path="trace" element={<WorkspacePage mode="trace" />} />
          <Route path="evaluations" element={<WorkspacePage mode="evaluations" />} />
          <Route path="settings" element={<WorkspacePage mode="settings" />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
