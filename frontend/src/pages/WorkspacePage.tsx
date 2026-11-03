import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { AlertCircle, Bot, FileCode2, Loader2, Play, ShieldCheck, Sparkles, Timer } from 'lucide-react'
import { fetchProjects, sendChatMessage } from '@/services/api'

// One chat box covers every analysis type: the backend supervisor routes each
// question to the matching specialist agent, so no separate pages are needed.
const capabilities = [
  { title: 'Explain architecture', hint: 'How parts fit together, data flow, dependencies', examples: ['Explain how the chat request flows from the API to the LLM', 'What is the overall architecture of this project?'] },
  { title: 'Find code', hint: 'Locate files, functions and classes with line numbers', examples: ['Where is the embedding model configured?', 'Which file defines the upload endpoint?'] },
  { title: 'Change impact', hint: 'Which files break if you modify something', examples: ['What would be affected if I change the embedding model?', 'Impact of removing the projects API'] },
  { title: 'Implementation plan', hint: 'Step-by-step plan for a new feature', examples: ['Create an implementation plan to add user login'] },
  { title: 'Test plan', hint: 'What to test for a feature or module', examples: ['Create a test plan for the ingestion pipeline'] },
  { title: 'Debug help', hint: 'Likely causes of an error or bug', examples: ['Debug: indexing fails with a connection refused error'] },
  { title: 'Code review', hint: 'Review of current working-tree changes', examples: ['Review the current code changes'] },
]

type ChatMessage = { role: 'user' | 'assistant'; content: string; seconds?: number; citations?: { file_path: string; start_line: number; end_line: number }[] }

export default function WorkspacePage() {
  const [input, setInput] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState(() => localStorage.getItem('repomind.selectedProjectId') || '')
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [elapsed, setElapsed] = useState(0)
  const { data: projects = [], isLoading: projectsLoading } = useQuery({ queryKey: ['projects'], queryFn: fetchProjects })
  const selectedProject = useMemo(() => projects.find((project) => project.id === selectedProjectId), [projects, selectedProjectId])
  const canAsk = Boolean(selectedProjectId) && selectedProject?.status === 'indexed'

  useEffect(() => {
    if (!selectedProjectId) {
      const indexed = projects.find((project) => project.status === 'indexed')
      if (indexed) setSelectedProjectId(indexed.id)
    }
  }, [projects, selectedProjectId])

  useEffect(() => {
    if (!selectedProjectId) return
    localStorage.setItem('repomind.selectedProjectId', selectedProjectId)
    setSessionId(crypto.randomUUID())
    setMessages([])
  }, [selectedProjectId])

  const chatMutation = useMutation({
    mutationFn: (question: string) => sendChatMessage(selectedProjectId, sessionId, question),
    onSuccess: (result) => {
      setMessages((current) => [...current, { role: 'assistant', content: result.response, citations: result.citations, seconds: elapsed }])
    },
  })

  // Live "waiting" timer so a slow local model never looks frozen.
  useEffect(() => {
    if (!chatMutation.isPending) return
    setElapsed(0)
    const started = Date.now()
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000)
    return () => clearInterval(timer)
  }, [chatMutation.isPending])

  const ask = (question: string) => {
    const text = question.trim()
    if (!text || !canAsk || chatMutation.isPending) return
    setMessages((current) => [...current, { role: 'user', content: text }])
    setInput('')
    chatMutation.mutate(text)
  }

  return (
    <div className="p-5 sm:p-8 max-w-7xl mx-auto space-y-6">
      <section className="rounded-2xl border border-border bg-card/70 p-6 sm:p-8 glow-primary">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-5">
          <div><div className="flex items-center gap-2 text-primary text-xs font-semibold uppercase tracking-widest"><Sparkles className="w-4 h-4" /> Agent workspace</div><h1 className="mt-2 text-3xl font-bold">Codebase Chat</h1><p className="mt-2 text-muted-foreground max-w-2xl">Ask source-grounded questions about an indexed repository. Architecture, navigation, impact, plans, tests and debugging all work from this one box.</p></div>
          <div className="rounded-xl bg-primary/10 border border-primary/20 p-3"><Bot className="text-primary" /></div>
        </div>
        <div className="mt-6 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
          <select aria-label="Selected repository" value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)} className="rounded-lg bg-secondary/60 border border-border px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-primary/50">
            <option value="">{projectsLoading ? 'Loading repositories…' : 'Select an indexed repository'}</option>
            {projects.map((project) => <option key={project.id} value={project.id} disabled={project.status !== 'indexed'}>{project.name} — {project.status}</option>)}
          </select>
          {selectedProject && <div className="rounded-lg border border-border bg-secondary/30 px-4 py-3 text-xs text-muted-foreground">{selectedProject.file_count} files · <span className="text-emerald-400 font-medium">{selectedProject.status}</span></div>}
        </div>
        <div className="mt-3 flex flex-col sm:flex-row gap-3">
          <input value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') ask(input) }} placeholder="Ask about the selected repository…" className="flex-1 rounded-lg bg-secondary/60 border border-border px-4 py-3 text-sm outline-none focus:ring-2 focus:ring-primary/50" />
          <button disabled={!canAsk || chatMutation.isPending || !input.trim()} onClick={() => ask(input)} className="inline-flex justify-center items-center gap-2 rounded-lg bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground disabled:opacity-50"><Play className="w-4 h-4" />{chatMutation.isPending ? 'Thinking…' : 'Send question'}</button>
        </div>
      </section>
      <div className="grid lg:grid-cols-3 gap-5">
        <section className="lg:col-span-2 rounded-xl border border-border bg-card p-5 min-h-[360px]">
          <div className="flex items-center justify-between"><h2 className="font-semibold">Conversation</h2><span className="text-xs text-muted-foreground">Read-only analysis</span></div>
          {!selectedProjectId ? <Empty message="Select an indexed repository to begin." /> : messages.length === 0 && !chatMutation.isPending ? <Empty message="Pick an example on the right, or ask your own question." /> : <div className="mt-5 space-y-4">
            {messages.map((message, index) => <div key={index} className={`rounded-xl border p-4 text-sm whitespace-pre-wrap ${message.role === 'user' ? 'ml-8 border-primary/20 bg-primary/5' : 'mr-3 border-border bg-secondary/20'}`}>
              <div className="mb-2 flex items-center justify-between text-xs font-semibold capitalize text-primary"><span>{message.role}</span>{message.seconds ? <span className="font-normal text-muted-foreground">answered in {message.seconds}s</span> : null}</div>
              {message.content}
              {message.citations?.length ? <div className="mt-3 border-t border-border pt-2 text-xs text-muted-foreground">Sources: {message.citations.map((citation, citationIndex) => <span key={citationIndex} className="mr-2 font-mono">{citation.file_path}:L{citation.start_line}-{citation.end_line}</span>)}</div> : null}
            </div>)}
            {chatMutation.isPending && <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" />RepoMind is retrieving code and generating a grounded answer…<span className="inline-flex items-center gap-1 font-mono text-xs text-primary"><Timer className="h-3.5 w-3.5" />{elapsed}s</span></div>}
            {chatMutation.isError && <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"><AlertCircle className="h-4 w-4" />{(chatMutation.error as any)?.response?.data?.detail || 'The chat request failed. Hover the status dot in the sidebar to see which service failed.'}</div>}
          </div>}
        </section>
        <aside className="rounded-xl border border-border bg-card p-5">
          <h2 className="font-semibold">What you can ask</h2>
          <ul className="mt-4 space-y-4">{capabilities.map((capability) => <li key={capability.title}>
            <p className="text-sm font-medium">{capability.title}</p>
            <p className="text-xs text-muted-foreground">{capability.hint}</p>
            <div className="mt-1.5 space-y-1">{capability.examples.map((example) => <button key={example} disabled={!canAsk || chatMutation.isPending} onClick={() => ask(example)} className="block w-full rounded-md border border-border/60 bg-secondary/30 px-2.5 py-1.5 text-left text-xs text-muted-foreground hover:border-primary/40 hover:text-foreground disabled:opacity-50">{example}</button>)}</div>
          </li>)}</ul>
          <div className="mt-6 pt-4 border-t border-border flex gap-2 text-xs text-muted-foreground"><ShieldCheck className="w-4 h-4 text-emerald-400" />Repository-safe controls enabled</div>
        </aside>
      </div>
    </div>
  )
}

function Empty({ message }: { message: string }) { return <div className="mt-20 text-center text-muted-foreground text-sm"><FileCode2 className="mx-auto mb-3 w-7 h-7 opacity-50" />{message}</div> }
