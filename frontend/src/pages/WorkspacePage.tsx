import { useState } from 'react'
import { Bot, CheckCircle2, ChevronRight, FileCode2, Play, ShieldCheck, Sparkles } from 'lucide-react'

const content: Record<string, { title: string; description: string; action: string; items: string[] }> = {
  chat: { title: 'Codebase Chat', description: 'Ask grounded questions about an indexed repository.', action: 'Send question', items: ['Cited answers', 'Session memory', 'Agent tool trace'] },
  repository: { title: 'Repository Explorer', description: 'Browse files, symbols, dependencies, and indexed context.', action: 'Inspect file', items: ['Source viewer', 'Symbol hierarchy', 'Dependency relationships'] },
  review: { title: 'Code Review', description: 'Review a pasted diff or repository working-tree change.', action: 'Review diff', items: ['Evidence-based findings', 'Severity labels', 'Changed-file context'] },
  plan: { title: 'Implementation Plan', description: 'Turn a feature request into a source-grounded delivery plan.', action: 'Generate plan', items: ['Affected files', 'Dependencies', 'Risks and tests'] },
  tests: { title: 'Test Plan', description: 'Generate unit, integration, API, edge, security, and regression coverage.', action: 'Create test plan', items: ['Coverage categories', 'Focused cases', 'Regression checklist'] },
  trace: { title: 'Agent Trace', description: 'Inspect safe execution metadata for each agent run.', action: 'Refresh trace', items: ['Supervisor duration', 'Tool status', 'Safe summaries'] },
  evaluations: { title: 'Evaluations', description: 'Review grounded-answer and citation benchmarks.', action: 'Run evaluation', items: ['Term recall', 'Citation recall', 'Pass/fail baseline'] },
  settings: { title: 'Settings', description: 'Configure your local RepoMind workspace.', action: 'Save settings', items: ['Local provider', 'Retrieval limits', 'Privacy controls'] },
}

export default function WorkspacePage({ mode }: { mode: keyof typeof content }) {
  const data = content[mode]
  const [input, setInput] = useState('')
  const [ran, setRan] = useState(false)
  return <div className="p-5 sm:p-8 max-w-7xl mx-auto space-y-6">
    <section className="rounded-2xl border border-border bg-card/70 p-6 sm:p-8 glow-primary">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-5"><div><div className="flex items-center gap-2 text-primary text-xs font-semibold uppercase tracking-widest"><Sparkles className="w-4 h-4" /> Agent workspace</div><h1 className="mt-2 text-3xl font-bold">{data.title}</h1><p className="mt-2 text-muted-foreground max-w-2xl">{data.description}</p></div><div className="rounded-xl bg-primary/10 border border-primary/20 p-3"><Bot className="text-primary" /></div></div>
      <div className="mt-6 flex flex-col sm:flex-row gap-3"><input value={input} onChange={e=>setInput(e.target.value)} placeholder={`Describe what you want ${data.title.toLowerCase()} to do…`} className="flex-1 rounded-lg bg-secondary/60 border border-border px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-primary/50"/><button onClick={()=>setRan(true)} className="inline-flex justify-center items-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground"><Play className="w-4 h-4" />{data.action}</button></div>
    </section>
    <div className="grid lg:grid-cols-3 gap-5"><section className="lg:col-span-2 rounded-xl border border-border bg-card p-5 min-h-[300px]"><div className="flex items-center justify-between"><h2 className="font-semibold">Workspace output</h2><span className="text-xs text-muted-foreground">Local-first</span></div>{ran ? <div className="mt-6 rounded-lg border border-primary/20 bg-primary/5 p-5 step-animate"><div className="flex gap-2 text-primary text-sm font-medium"><CheckCircle2 className="w-4 h-4" />Request ready for the RepoMind agent pipeline</div><p className="mt-3 text-sm text-muted-foreground">{input || 'Select a repository and provide a request to begin.'}</p><div className="mt-5 font-mono text-xs text-muted-foreground">supervisor → retrieve → tools → grounded response</div></div> : <div className="mt-20 text-center text-muted-foreground text-sm"><FileCode2 className="mx-auto mb-3 w-7 h-7 opacity-50"/>Enter a request to start an interactive run.</div>}</section><aside className="rounded-xl border border-border bg-card p-5"><h2 className="font-semibold">Capabilities</h2><ul className="mt-4 space-y-3">{data.items.map(item=><li key={item} className="flex gap-2 text-sm text-muted-foreground"><ChevronRight className="w-4 h-4 text-accent shrink-0"/>{item}</li>)}</ul><div className="mt-8 pt-4 border-t border-border flex gap-2 text-xs text-muted-foreground"><ShieldCheck className="w-4 h-4 text-emerald-400"/>Repository-safe controls enabled</div></aside></div>
  </div>
}
