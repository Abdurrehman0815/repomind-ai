import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { fetchHealthFull } from '@/services/api'
import { LayoutDashboard, FolderGit2, MessageSquare, Brain } from 'lucide-react'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/projects', icon: FolderGit2, label: 'Projects' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
]

export default function Sidebar() {
  const { data: health } = useQuery({ queryKey: ['health-full'], queryFn: fetchHealthFull, refetchInterval: 30000 })
  const isHealthy = health?.status === 'healthy'
  const dotColor = !health ? 'bg-amber-400' : isHealthy ? 'bg-emerald-400' : health.status === 'degraded' ? 'bg-amber-400' : 'bg-rose-500'
  const label = !health ? 'Checking services' : isHealthy ? 'Services ready' : health.status === 'degraded' ? 'Some services degraded' : 'Services unavailable'
  // Native tooltip: one line per component, failures first, e.g. "llm: azure_foundry: gpt-4.1-mini ✓".
  const details = Object.entries(health?.components ?? {})
    .sort(([, a], [, b]) => Number(a.status === 'ok') - Number(b.status === 'ok'))
    .map(([name, c]) => `${name}: ${c.status === 'ok' ? '✓' : '✗ ' + c.status}${c.message ? ' — ' + c.message : ''}`)
    .join('\n')
  return (
    <aside className="flex flex-col w-16 lg:w-56 h-full border-r border-border bg-card shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-3 py-4 border-b border-border h-14">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 shrink-0">
          <Brain className="w-4 h-4 text-primary" />
        </div>
        <span className="hidden lg:block text-sm font-semibold text-gradient tracking-tight">
          RepoMind AI
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-2.5 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            <span className="hidden lg:block">{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Compact runtime indicator */}
      <div className="p-3 border-t border-border">
        <div title={details || label} className="flex items-center gap-2 text-xs text-muted-foreground cursor-help">
          <span className={`h-2 w-2 rounded-full shrink-0 ${dotColor}`} />
          <span className="hidden lg:inline">{label}</span>
        </div>
      </div>
    </aside>
  )
}
