import { useQuery } from '@tanstack/react-query'
import { fetchHealthFull, fetchProjects } from '@/services/api'
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FolderGit2,
  Cpu,
  Layers,
  Sparkles,
  ArrowRight,
} from 'lucide-react'
import { Link } from 'react-router-dom'

export default function DashboardPage() {
  const { data: health, isLoading: healthLoading, isError: healthError } = useQuery({
    queryKey: ['health-full'],
    queryFn: fetchHealthFull,
    refetchInterval: 15000,
  })

  const { data: projects, isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8 animate-in fade-in duration-300">
      {/* Top Banner / Hero */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-primary/10 via-accent/10 to-transparent border border-border/80 p-6 sm:p-8 backdrop-blur-md">
        <div className="relative z-10 max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/20 border border-primary/30 text-xs font-medium text-primary">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Agentic Codebase Intelligence</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-foreground">
            RepoMind AI Workspace
          </h1>
          <p className="text-muted-foreground text-sm sm:text-base leading-relaxed">
            Local-first AI copilot for exploring, indexing, and executing agentic reasoning
            across your entire repository with full code citation provenance.
          </p>
          <div className="pt-2 flex items-center gap-3">
            <Link
              to="/projects"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition shadow-lg shadow-primary/20"
            >
              <FolderGit2 className="w-4 h-4" />
              Manage Repositories
              <ArrowRight className="w-4 h-4 ml-1" />
            </Link>
          </div>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Card 1: System Health */}
        <div className="rounded-xl border border-border/70 bg-card/60 backdrop-blur-sm p-6 shadow-sm hover:border-border transition">
          <div className="flex items-center justify-between pb-3">
            <span className="text-sm font-medium text-muted-foreground">System Health</span>
            <Activity className="w-4 h-4 text-primary" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold capitalize">
              {healthLoading ? 'Checking...' : healthError ? 'Offline' : health?.status || 'Unknown'}
            </span>
            {health && (
              <span className="text-xs text-muted-foreground">
                ({health.uptime_seconds}s uptime)
              </span>
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Environment: <span className="font-mono text-foreground">{health?.environment || 'development'}</span>
          </p>
        </div>

        {/* Card 2: Active Repositories */}
        <div className="rounded-xl border border-border/70 bg-card/60 backdrop-blur-sm p-6 shadow-sm hover:border-border transition">
          <div className="flex items-center justify-between pb-3">
            <span className="text-sm font-medium text-muted-foreground">Repositories</span>
            <FolderGit2 className="w-4 h-4 text-accent" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold">
              {projectsLoading ? '...' : projects?.length ?? 0}
            </span>
            <span className="text-xs text-muted-foreground">registered projects</span>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Local workspace path configured and monitored
          </p>
        </div>

        {/* Card 3: Backend Version */}
        <div className="rounded-xl border border-border/70 bg-card/60 backdrop-blur-sm p-6 shadow-sm hover:border-border transition">
          <div className="flex items-center justify-between pb-3">
            <span className="text-sm font-medium text-muted-foreground">Engine Version</span>
            <Cpu className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold font-mono">
              v{health?.version || '0.1.0'}
            </span>
            <span className="text-xs text-emerald-400 font-medium">Phase 1 Monorepo</span>
          </div>
          <p className="text-xs text-muted-foreground mt-2">
            Multi-agent architecture ready
          </p>
        </div>
      </div>

      {/* Subsystem Diagnostics */}
      <div className="rounded-xl border border-border/70 bg-card/60 backdrop-blur-sm p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Layers className="w-5 h-5 text-primary" />
          Subsystem Status
        </h2>

        {healthLoading ? (
          <div className="text-sm text-muted-foreground py-4">Probing subsystem endpoints...</div>
        ) : healthError ? (
          <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            Backend API is not reachable at configured endpoint. Verify the server is running on port 8000.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(health?.components || {}).map(([name, comp]) => {
              const isOk = comp.status === 'ok'
              const isDegraded = comp.status === 'degraded'
              return (
                <div
                  key={name}
                  className="p-4 rounded-lg border border-border/50 bg-secondary/20 flex flex-col justify-between"
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold capitalize">{name}</span>
                    {isOk ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : isDegraded ? (
                      <AlertTriangle className="w-4 h-4 text-amber-400" />
                    ) : (
                      <XCircle className="w-4 h-4 text-rose-400" />
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground space-y-1">
                    <div>
                      Status: <span className="font-mono text-foreground">{comp.status}</span>
                    </div>
                    {comp.latency_ms != null && (
                      <div>Latency: {comp.latency_ms}ms</div>
                    )}
                    {comp.message && (
                      <div className="text-[11px] truncate text-muted-foreground/80">
                        {comp.message}
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
