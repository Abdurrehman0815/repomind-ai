import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FolderGit2,
  MessageSquare,
  BarChart3,
  Settings,
  Brain,
  FileCode2, GitPullRequest, ListChecks, Route, ClipboardCheck,
} from 'lucide-react'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/projects', icon: FolderGit2, label: 'Projects' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/repository', icon: FileCode2, label: 'Repository' },
  { to: '/review', icon: GitPullRequest, label: 'Code Review' },
  { to: '/plan', icon: ListChecks, label: 'Implementation Plan' },
  { to: '/tests', icon: ClipboardCheck, label: 'Test Plan' },
  { to: '/trace', icon: Route, label: 'Agent Trace' },
  { to: '/evaluations', icon: BarChart3, label: 'Evaluations' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
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

      {/* Version badge */}
      <div className="p-3 border-t border-border">
        <p className="hidden lg:block text-xs text-muted-foreground">v0.1.0 · Phase 1</p>
      </div>
    </aside>
  )
}
