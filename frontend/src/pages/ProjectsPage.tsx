import { useQuery } from '@tanstack/react-query'
import { fetchProjects } from '@/services/api'
import {
  FolderGit2,
  Plus,
  GitBranch,
  FileCode,
  Clock,
} from 'lucide-react'

export default function ProjectsPage() {
  const { data: projects, isLoading, isError } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6 animate-in fade-in duration-300">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Repositories & Codebases
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Import and inspect local software repositories for semantic indexing and agentic analysis.
          </p>
        </div>
        <div>
          <button
            type="button"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition shadow"
            onClick={() => alert('Repository import workflow configured for Phase 3')}
          >
            <Plus className="w-4 h-4" />
            Import Repository
          </button>
        </div>
      </div>

      {/* Projects List / Empty State */}
      {isLoading ? (
        <div className="text-center py-16 text-muted-foreground">Loading repositories...</div>
      ) : isError ? (
        <div className="p-6 rounded-xl border border-destructive/20 bg-destructive/10 text-destructive text-sm text-center">
          Unable to fetch projects from backend.
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
            onClick={() => alert('Repository import will be enabled in Phase 3')}
          >
            <Plus className="w-3.5 h-3.5" />
            Connect First Project
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {projects?.map((project) => (
            <div
              key={project.id}
              className="p-6 rounded-xl border border-border bg-card/60 backdrop-blur-sm hover:border-primary/50 transition flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <GitBranch className="w-4 h-4 text-primary" />
                    <span className="font-semibold text-foreground">{project.name}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-secondary text-secondary-foreground">
                    {project.status}
                  </span>
                </div>
                <p className="text-xs font-mono text-muted-foreground truncate mb-4">
                  {project.path}
                </p>
              </div>

              <div className="pt-4 border-t border-border/50 flex items-center justify-between text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <FileCode className="w-3.5 h-3.5" />
                  {project.file_count ?? 0} files
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5" />
                  {new Date(project.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
