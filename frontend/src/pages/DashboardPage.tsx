import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, FolderGit2, MessageSquare, Sparkles } from 'lucide-react'
import { fetchProjects } from '@/services/api'

export default function DashboardPage() {
  const { data: projects = [] } = useQuery({ queryKey: ['projects'], queryFn: fetchProjects })
  const indexed = projects.filter((project) => project.status === 'indexed')

  return <div className="p-8 max-w-7xl mx-auto space-y-7 animate-in fade-in duration-300">
    <section className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-primary/10 via-accent/10 to-transparent border border-border/80 p-8">
      <div className="max-w-2xl space-y-4"><div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/20 border border-primary/30 text-xs font-medium text-primary"><Sparkles className="w-3.5 h-3.5" />Repository intelligence workspace</div><h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">Understand your codebase with grounded AI.</h1><p className="text-muted-foreground text-sm sm:text-base leading-relaxed">Import a repository, let RepoMind index it, then ask questions with source citations. Analysis remains read-only and repository-safe.</p><div className="pt-2 flex flex-wrap gap-3"><Link to="/projects" className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary text-primary-foreground"><FolderGit2 className="w-4 h-4" />Manage repositories<ArrowRight className="w-4 h-4" /></Link>{indexed.length > 0 && <Link to="/chat" className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg border border-border hover:bg-secondary"><MessageSquare className="w-4 h-4" />Ask your codebase</Link>}</div></div>
    </section>
    <section className="grid gap-5 md:grid-cols-2"><div className="rounded-xl border border-border bg-card p-6"><p className="text-sm text-muted-foreground">Indexed repositories</p><p className="mt-2 text-3xl font-bold">{indexed.length}</p><p className="mt-2 text-xs text-muted-foreground">{projects.length} total repositories connected</p></div><div className="rounded-xl border border-border bg-card p-6"><p className="text-sm text-muted-foreground">Ready to analyse</p><p className="mt-2 text-lg font-semibold">{indexed.length ? indexed.map((project) => project.name).join(', ') : 'No indexed repository yet'}</p><p className="mt-2 text-xs text-muted-foreground">Open Chat and pick a repository to start asking questions.</p></div></section>
  </div>
}
