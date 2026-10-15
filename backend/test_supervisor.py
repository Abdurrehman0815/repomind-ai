import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

# Import the supervisor service
from app.services.supervisor_service import SupervisorService
from app.models.chat import ChatSession, ChatMessage
from app.models.project import Project
from app.services.citation_service import CitationResponse

async def test_supervisor_service():
    # Create a mock session
    mock_session = AsyncMock(spec=AsyncSession)

    # Create the supervisor service
    supervisor = SupervisorService(mock_session)

    # Mock the chat repository
    mock_chat_session = MagicMock(spec=ChatSession)
    mock_chat_session.id = 1
    mock_chat_session.project_id = "test-project"
    supervisor.chat_repo = AsyncMock()
    supervisor.chat_repo.get_or_create_session = AsyncMock(return_value=mock_chat_session)

    def add_message_side_effect(**kwargs):
        msg = MagicMock(spec=ChatMessage)
        msg.id = kwargs.get("temp_id", 0)
        msg.role = kwargs.get("role")
        msg.content = kwargs.get("content")
        msg.citations = kwargs.get("citations", [])
        return msg
    supervisor.chat_repo.add_message = AsyncMock(side_effect=add_message_side_effect)

    # Mock the project repository
    mock_project = MagicMock(spec=Project)
    mock_project.id = "test-project"
    mock_project.path = "/tmp/test"
    supervisor.project_repo = AsyncMock()
    supervisor.project_repo.get = AsyncMock(return_value=mock_project)

    # Mock the retrieval service
    supervisor.retrieval_service = AsyncMock()
    mock_chunk = MagicMock()
    mock_chunk.content = "def test_function():\n    return 42"
    mock_chunk.file_id = 1
    mock_chunk.start_line = 1
    mock_chunk.end_line = 2
    supervisor.retrieval_service.hybrid_search = AsyncMock(return_value=[(mock_chunk, 0.9)])

    # Mock the citation service
    supervisor.citation_service = AsyncMock()
    mock_citation = CitationResponse(
        file_path="test.py",
        start_line=1,
        end_line=10,
        symbol="test_func",
        file_hash="abc123",
        repository_commit="def456",
        is_stale=False
    )
    supervisor.citation_service.create_citation_from_chunk = AsyncMock(return_value=mock_citation)
    supervisor.citation_service.validate_citation = AsyncMock(return_value=(True, ""))

    # Mock the LLM provider
    with patch('app.services.supervisor_service.get_llm_provider') as mock_get_llm_provider:
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock()
        mock_provider.generate.return_value = MagicMock(content="This is a test response.")
        mock_provider.stream = AsyncMock()
        # Create an async iterator for the stream
        async def mock_stream(*args, **kwargs):
            yield MagicMock(content="This is a ", is_final=False)
            yield MagicMock(content="test response.", is_final=True)
        mock_provider.stream = mock_stream
        mock_get_llm_provider.return_value = mock_provider

        # Test non-streaming
        result = await supervisor.process_message(
            project_id="test-project",
            session_id="test-session",
            user_message="What is the test?",
            stream=False
        )

        print("Non-streaming result:")
        print(result)

        # Check that the result has the expected keys
        assert "session_id" in result
        assert "message_id" in result
        assert "response" in result
        assert "intent" in result
        assert "citations" in result
        assert result["stream"] == False

        # Check that the response is not the fallback message
        assert result["response"] != "I could not find sufficient evidence in the codebase to answer this question."

        # Test streaming
        result_stream = await supervisor.process_message(
            project_id="test-project",
            session_id="test-session",
            user_message="What is the test?",
            stream=True
        )

        print("\nStreaming result:")
        print(result_stream)

        assert "session_id" in result_stream
        assert "message_id" in result_stream
        assert "intent" in result_stream
        assert result_stream["stream"] == True
        assert "response_generator" in result_stream

        # Consume the generator
        chunks = []
        async for chunk in result_stream["response_generator"]:
            chunks.append(chunk)

        print("Chunks:", chunks)
        # Check that we got chunks
        assert len(chunks) > 0
        # Check that the final chunk has is_final=True
        assert chunks[-1].is_final == True

        print("\nAll tests passed!")

if __name__ == "__main__":
    asyncio.run(test_supervisor_service())