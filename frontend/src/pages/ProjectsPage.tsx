import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchProjects,
  createProject,
  scanProject,
  deleteProject,
} from '@/services/api'
import type { Project } from '@/types'
import {
  FolderGit2,
  Plus,
  GitBranch,
  FileCode,
  Clock,
  RefreshCw,
  Trash2,
  HardDrive,
  X,
  AlertCircle,
  Loader2,
  CheckCircle2,
} from 'lucide-react'

export default function ProjectsPage() {
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [repoPath, setRepoPath] = useState('')
  const [repoName, setRepoName] = useState('')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const { data: projects, isLoading, isError } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })

  // Create Project Mutation
  const createMutation = useMutation({
    mutationFn: () => createProject(repoPath, repoName),
    onSuccess: (newProj) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setIsModalOpen(false)
      setRepoPath('')
      setRepoName('')
      setErrorMessage(null)
      setSuccessMessage(`Repository '${newProj.name}' imported with ${newProj.file_count} files!`)
      setTimeout(() => setSuccessMessage(null), 5000)
    },
    onError: (err: any) => {
      const msg = err.response?.data?.detail || err.message || 'Failed to import repository.'
      setErrorMessage(msg)
    },
  })

  // Scan Project Mutation
  const scanMutation = useMutation({
    mutationFn: (projectId: string) => scanProject(projectId),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      const s = res.summary
      setSuccessMessage(
        `Scan complete: ${s.added_files} added, ${s.modified_files} modified, ${s.unchanged_files} unchanged.`
      )
      setTimeout(() => setSuccessMessage(null), 5000)
    },
    onError: (err: any) => {
      setErrorMessage(err.response?.data?.detail || 'Failed to scan repository.')
    },
  })

  // Delete Project Mutation
  const deleteMutation = useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const handleImportSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoPath.trim()) {
      setErrorMessage('Repository path cannot be empty.')
      return
    }
    setErrorMessage(null)
    createMutation.mutate()
  }

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Top Banner / Alerts */}
      {successMessage && (
        <div className="p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-emerald-300 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)}>
            <X className="w-4 h-4 hover:opacity-75" />
          </button>
        </div>
      )}

      {errorMessage && !isModalOpen && (
        <div className="p-4 rounded-xl border border-destructive/20 bg-destructive/10 text-destructive text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)}>
            <X className="w-4 h-4 hover:opacity-75" />
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Repositories & Codebases
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Import, scan, and inspect local repositories with automated language detection and AST symbol mapping.
          </p>
        </div>
        <div>
          <button
            type="button"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition shadow"
            onClick={() => {
              setErrorMessage(null)
              setIsModalOpen(true)
            }}
          >
            <Plus className="w-4 h-4" />
            Import Repository
          </button>
        </div>
      </div>

      {/* Projects List / Empty State */}
      {isLoading ? (
        <div className="text-center py-16 text-muted-foreground flex flex-col items-center gap-2">
          <Loader2 className="w-6 h-6 animate-spin text-primary" />
          <span>Scanning repository catalog...</span>
        </div>
      ) : isError ? (
        <div className="p-6 rounded-xl border border-destructive/20 bg-destructive/10 text-destructive text-sm text-center">
          Unable to fetch projects from backend. Verify that the FastAPI service is running.
        </div>
      ) : projects?.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-border bg-card/40 backdrop-blur-sm space-y-4">
          <div className="w-12 h-12 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
            <FolderGit2 className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h3 className="text-base font-semibold text-foreground">No repositories indexed yet</h3>
            <p className="text-sm text-muted-foreground max-w-md">
              Start by connecting a local git repository. RepoMind AI will parse AST symbols, extract semantic chunks, and build the dependency graph.
            </p>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 transition"
            onClick={() => setIsModalOpen(true)}
          >
            <Plus className="w-3.5 h-3.5" />
            Connect First Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects?.map((project: Project) => (
            <div
              key={project.id}
              className="p-6 rounded-xl border border-border bg-card/60 backdrop-blur-sm hover:border-primary/50 transition flex flex-col justify-between group shadow-sm"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-primary" />
                    <span className="font-semibold text-foreground truncate max-w-[180px]">
                      {project.name}
                    </span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-secondary text-secondary-foreground capitalize">
                    {project.status}
                  </span>
                </div>
                <p className="text-xs font-mono text-muted-foreground truncate mb-4" title={project.path}>
                  {project.path}
                </p>
              </div>

              <div className="space-y-3 pt-3 border-t border-border/50">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    <FileCode className="w-3.5 h-3.5 text-primary" />
                    {project.file_count ?? 0} files
                  </span>
                  <span className="flex items-center gap-1.5">
                    <HardDrive className="w-3.5 h-3.5 text-accent" />
                    {formatBytes(project.total_size_bytes ?? 0)}
                  </span>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    {new Date(project.created_at).toLocaleDateString()}
                  </span>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      title="Incremental Re-scan"
                      disabled={scanMutation.isPending}
                      className="p-1.5 rounded-md hover:bg-secondary text-muted-foreground hover:text-foreground transition disabled:opacity-50"
                      onClick={() => scanMutation.mutate(project.id)}
                    >
                      <RefreshCw
                        className={`w-3.5 h-3.5 ${
                          scanMutation.isPending ? 'animate-spin text-primary' : ''
                        }`}
                      />
                    </button>
                    <button
                      type="button"
                      title="Delete Repository"
                      disabled={deleteMutation.isPending}
                      className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition"
                      onClick={() => {
                        if (confirm(`Remove project '${project.name}' from RepoMind AI?`)) {
                          deleteMutation.mutate(project.id)
                        }
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Import Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-border pb-3">
              <div className="flex items-center gap-2">
                <FolderGit2 className="w-5 h-5 text-primary" />
                <h3 className="text-lg font-semibold text-foreground">Import Local Repository</h3>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-muted-foreground hover:text-foreground p-1 rounded-md"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {errorMessage && (
              <div className="p-3 rounded-lg border border-destructive/20 bg-destructive/10 text-destructive text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}

            <form onSubmit={handleImportSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Repository Directory Path <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. C:\Users\name\projects\my-app or /home/name/my-app"
                  value={repoPath}
                  onChange={(e) => setRepoPath(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-lg bg-secondary/50 border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary font-mono placeholder:font-sans placeholder:text-muted-foreground"
                  autoFocus
                />
                <p className="text-[11px] text-muted-foreground mt-1">
                  Local path on the machine running RepoMind AI. .gitignore rules will be applied automatically.
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-foreground mb-1.5">
                  Project Display Name <span className="text-muted-foreground font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  placeholder="Defaults to folder name if left blank"
                  value={repoName}
                  onChange={(e) => setRepoName(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-lg bg-secondary/50 border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-medium rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition shadow disabled:opacity-50"
                >
                  {createMutation.isPending ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      Scanning Files...
                    </>
                  ) : (
                    <>
                      <FolderGit2 className="w-3.5 h-3.5" />
                      Import & Scan
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
