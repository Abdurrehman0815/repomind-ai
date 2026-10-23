from __future__ import annotations
import pytest
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.services.memory_service import MemoryService

@pytest.mark.asyncio
async def test_project_memory_is_bounded_and_persists(test_db_session, tmp_path):
    project = await ProjectRepository(test_db_session).create(name="Memory", path=str(tmp_path / "memory-repo"))
    service = MemoryService(test_db_session)
    memory = await service.update_project_memory(project.id, summary="Repo summary", modules=["app/auth.py"], plan="Add MFA", feedback="Useful")
    assert memory["summary"] == "Repo summary"
    assert memory["important_modules"] == ["app/auth.py"]
    assert (await service.get_project_memory(project.id))["previous_plans"] == ["Add MFA"]

@pytest.mark.asyncio
async def test_session_memory_is_isolated(test_db_session, tmp_path):
    project = await ProjectRepository(test_db_session).create(name="Isolation", path=str(tmp_path / "isolation-repo"))
    service = MemoryService(test_db_session)
    first = await service.chat_repo.get_or_create_session("session-one", project.id)
    second = await service.chat_repo.get_or_create_session("session-two", project.id)
    await service.chat_repo.add_message(first.id, "user", "remember MFA")
    await service.chat_repo.add_message(second.id, "user", "remember billing")
    assert (await service.get_session_memory(first.id))[0]["content"] == "remember MFA"
