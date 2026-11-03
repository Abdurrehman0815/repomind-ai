import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchProjects,
  createProject,
  uploadProject,
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
  const [folderFiles, setFolderFiles] = useState<File[]>([])
  const [uploadPercent, setUploadPercent] = useState(0)
  const folderInputRef = useRef<HTMLInputElement>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  const { data: projects, isLoading, isError } = useQuery<Project[]>({
    queryKey: ['projects'],
    queryFn: fetchProjects,
    // Keep the visible indexing state current without requiring a manual refresh.
    refetchInterval: 3000,
  })

  // Create Project Mutation
  const createMutation = useMutation({
    mutationFn: () =>
      folderFiles.length > 0
        ? uploadProject(folderFiles, repoName.trim() || undefined, setUploadPercent)
        : createProject(repoPath, repoName),
    onSuccess: (newProj) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setIsModalOpen(false)
      setRepoPath('')
      setRepoName('')
      setFolderFiles([])
      setUploadPercent(0)
      setErrorMessage(null)
      setSuccessMessage(`Repository '${newProj.name}' was added. Indexing has started; progress is shown on its card.`)
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

  const activeIndexingProject = projects?.find((p) => p.status === 'indexing')
  const isActivelyIndexing = Boolean(activeIndexingProject || createMutation.isPending || scanMutation.isPending)

  const handleImportSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!repoPath.trim() && folderFiles.length === 0) {
      setErrorMessage('Enter a GitHub URL / path, or choose a folder from your computer.')
      return
    }
    setErrorMessage(null)
    createMutation.mutate()
  }

  const handleFolderPicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const skip = /(^|\/)(\.git|node_modules|venv|\.venv|__pycache__|dist|build|\.next)\//
    const picked = Array.from(event.target.files ?? []).filter(
      (file) => !skip.test(file.webkitRelativePath) && file.size <= 10 * 1024 * 1024
    )
    setFolderFiles(picked)
    if (picked.length > 0) {
      setRepoPath('')
      if (!repoName.trim()) setRepoName(picked[0].webkitRelativePath.split('/')[0])
    }
  }

  const formatDuration = (seconds: number) => {
    if (seconds < 60) return `${Math.max(1, Math.round(seconds))}s`
    return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`
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
            Import public GitHub repositories or local workspaces, then index them for code search and agent analysis.
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

      {/* Prominent Indexing Activity Card */}
      {isActivelyIndexing && (() => {
        const fileCount = activeIndexingProject?.file_count ?? 0
        const indexing = activeIndexingProject?.metadata?.indexing
        const done = indexing?.files_done ?? 0
        const total = indexing?.files_total ?? 0
        const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
        const elapsed = indexing?.started_at ? Date.now() / 1000 - indexing.started_at : 0
        const phaseLabel =
          indexing?.phase === 'cloning' ? 'Cloning repository'
          : indexing?.phase === 'scanning' ? 'Scanning files'
          : indexing?.phase === 'embedding' ? 'Parsing and embedding'
          : 'Starting'
        const timeLabel =
          indexing?.phase === 'embedding' && done >= 2 && elapsed > 0
            ? `~${formatDuration(((total - done) * elapsed) / done)} left`
            : 'estimating…'
        return (
          <div className="p-5 rounded-2xl border border-primary/40 bg-gradient-to-r from-primary/10 via-accent/5 to-primary/10 shadow-lg backdrop-blur-md space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
                </span>
                <div>
                  <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
                    <span>Indexing Activity</span>
                    <span className="text-xs font-normal text-muted-foreground font-mono">
                      ({activeIndexingProject?.name || repoName || 'Active Task'})
                    </span>
                  </h3>
                  <p className="text-xs text-muted-foreground font-mono truncate max-w-lg">
                    {activeIndexingProject?.path || repoPath || 'Processing codebase pipeline...'}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-2 flex-wrap">
                {fileCount > 0 && (
                  <span className="px-3 py-1 rounded-full text-xs font-medium bg-accent/10 text-accent border border-accent/20">
                    ⏱ {timeLabel} · {total > 0 ? `${done}/${total} files` : `${fileCount} files`}
                  </span>
                )}
                <span className="px-3 py-1 rounded-full text-xs font-medium bg-primary/20 text-primary border border-primary/30 flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>{phaseLabel}</span>
                </span>
              </div>
            </div>

            {/* Indeterminate Progress Bar */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">
                  Extracting AST symbols, chunking source, and generating vector embeddings...
                </span>
                <span className="font-mono text-primary font-medium flex items-center gap-1 ml-3 shrink-0">
                  {total > 0 ? `${percent}%` : <Loader2 className="w-3 h-3 animate-spin" />}
                </span>
              </div>
              <div className="h-2.5 w-full bg-secondary/80 rounded-full overflow-hidden relative border border-primary/20 shadow-inner">
                {total > 0 ? (
                  <div className="h-full bg-gradient-to-r from-primary via-accent to-primary rounded-full transition-all duration-500" style={{ width: `${percent}%` }} />
                ) : (
                  <div className="h-full w-1/3 bg-gradient-to-r from-primary via-accent to-primary rounded-full animate-indeterminate-bar shadow-[0_0_12px_rgba(59,130,246,0.6)]" />
                )}
              </div>
              <p className="text-[11px] text-muted-foreground">
                This page auto-refreshes every 3s. When indexing completes, status will change to <span className="text-emerald-400 font-medium">indexed</span> and you can start asking questions in Chat.
              </p>
            </div>

            {/* Pipeline Stages */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pt-1 text-xs">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card/60 border border-emerald-500/30">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span className="text-foreground">1. Ingestion & File Sync ✓</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card/60 border border-primary/30">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-accent shrink-0" />
                <span className="text-foreground">2. AST Symbols & Graph</span>
              </div>
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-card/60 border border-primary/30">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-primary shrink-0" />
                <span className="text-foreground">3. Vector Embeddings</span>
              </div>
            </div>
          </div>
        )
      })()}

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
              Connect a public GitHub repository or a local workspace. RepoMind AI will parse symbols, extract semantic chunks, generate embeddings, and build the dependency graph.
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
                  <span className={`px-2 py-0.5 rounded text-[11px] font-mono capitalize ${
                    project.status === 'indexed'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : project.status === 'indexing'
                      ? 'bg-primary/10 text-primary border border-primary/20 animate-pulse'
                      : 'bg-secondary text-secondary-foreground'
                  }`}>
                    {project.status}
                  </span>
                </div>
                <p className="text-xs font-mono text-muted-foreground truncate mb-4" title={project.path}>
                  {project.path}
                </p>
              </div>

              <div className="space-y-3 pt-3 border-t border-border/50">
                {(scanMutation.isPending && scanMutation.variables === project.id) || project.status === 'indexing' ? (
                  <div className="space-y-2 rounded-lg border border-primary/30 bg-primary/5 p-3">
                    <div className="flex items-center justify-between text-xs text-primary font-medium">
                      <span>Indexing repository…</span>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    </div>
                    {/* Indeterminate Animated Progress Bar */}
                    <div className="h-2 w-full bg-secondary/80 rounded-full overflow-hidden relative border border-primary/20">
                      <div className="h-full w-1/3 bg-gradient-to-r from-primary via-accent to-primary rounded-full animate-indeterminate-bar shadow-[0_0_10px_rgba(59,130,246,0.5)]" />
                    </div>
                    <p className="text-[11px] text-muted-foreground">Scanning files, parsing AST symbols, and creating vector embeddings.</p>
                  </div>
                ) : null}
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
                <h3 className="text-lg font-semibold text-foreground">Import Repository</h3>
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
                  Repository Path or Public GitHub URL <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  placeholder="https://github.com/owner/repository or C:\Users\name\projects\my-app"
                  value={repoPath}
                  onChange={(e) => setRepoPath(e.target.value)}
                  className="w-full px-3.5 py-2 rounded-lg bg-secondary/50 border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary font-mono placeholder:font-sans placeholder:text-muted-foreground"
                  autoFocus
                />
                <p className="text-[11px] text-muted-foreground mt-1">
                  Use a public GitHub URL or a local path visible to the backend container. GitHub repositories are cloned into RepoMind's managed workspace.
                </p>
              </div>

              <div className="flex items-center gap-3 text-[11px] text-muted-foreground"><span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" /></div>

              <div>
                <input
                  ref={folderInputRef}
                  type="file"
                  className="hidden"
                  onChange={handleFolderPicked}
                  {...({ webkitdirectory: '', directory: '', multiple: true } as Record<string, unknown>)}
                />
                <button
                  type="button"
                  onClick={() => folderInputRef.current?.click()}
                  className="w-full inline-flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-lg border border-dashed border-primary/40 bg-primary/5 text-sm text-primary hover:bg-primary/10 transition"
                >
                  <HardDrive className="w-4 h-4" />
                  {folderFiles.length > 0 ? `${folderFiles.length} files selected — choose a different folder` : 'Choose a folder from this computer'}
                </button>
                <p className="text-[11px] text-muted-foreground mt-1">
                  The folder is copied into RepoMind's workspace (your original stays untouched). .git, node_modules, venv and build output are skipped automatically.
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

              {createMutation.isPending && (
                <div className="space-y-2 p-3 rounded-xl border border-primary/30 bg-primary/5">
                  <div className="flex items-center justify-between text-xs text-primary font-medium">
                    <span className="flex items-center gap-1.5">
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      {folderFiles.length > 0 ? `Uploading folder… ${uploadPercent}%` : 'Registering repository and initiating indexing pipeline...'}
                    </span>
                  </div>
                  <div className="h-2 w-full bg-secondary/80 rounded-full overflow-hidden relative border border-primary/20">
                    <div className="h-full w-1/3 bg-gradient-to-r from-primary via-accent to-primary rounded-full animate-indeterminate-bar shadow-[0_0_10px_rgba(59,130,246,0.5)]" />
                  </div>
                </div>
              )}

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  disabled={createMutation.isPending}
                  className="px-4 py-2 text-xs font-medium rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground transition disabled:opacity-50"
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
                      Importing & Indexing...
                    </>
                  ) : (
                    <>
                      <FolderGit2 className="w-3.5 h-3.5" />
                      Import & Index
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
