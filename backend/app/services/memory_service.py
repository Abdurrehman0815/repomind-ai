"""Phase 23: bounded, project-scoped conversation memory."""
from __future__ import annotations

from typing import Any
from app.repositories.chat_repository import ChatRepository
from app.repositories.project_repository import ProjectRepository


class MemoryService:
    """Keeps session memory isolated and project memory bounded in metadata."""
    def __init__(self, session: Any) -> None:
        self.chat_repo = ChatRepository(session)
        self.project_repo = ProjectRepository(session)
        self.session = session

    async def get_session_memory(self, session_id: str, limit: int = 8) -> list[dict[str, str]]:
        messages = await self.chat_repo.get_session_messages(session_id, limit=min(max(limit, 1), 20))
        return [{"role": item.role, "content": item.content[:2000]} for item in messages]

    async def get_project_memory(self, project_id: str) -> dict[str, Any]:
        project = await self.project_repo.get_by_id(project_id)
        if project is None:
            return {}
        return dict(project.metadata_.get("memory", {}))

    async def update_project_memory(self, project_id: str, *, summary: str | None = None, modules: list[str] | None = None, plan: str | None = None, feedback: str | None = None) -> dict[str, Any]:
        project = await self.project_repo.get_by_id(project_id)
        if project is None:
            raise ValueError("Project not found")
        metadata = dict(project.metadata_ or {})
        memory = dict(metadata.get("memory", {}))
        if summary: memory["summary"] = summary[:4000]
        if modules: memory["important_modules"] = list(dict.fromkeys(modules))[:30]
        for key, value in (("previous_plans", plan), ("user_feedback", feedback)):
            if value:
                memory[key] = (memory.get(key, []) + [value[:2000]])[-10:]
        metadata["memory"] = memory
        project.metadata_ = metadata
        await self.session.flush()
        return memory
