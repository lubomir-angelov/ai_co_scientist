import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from tools_registry import ToolsRegistry, ToolSchema


@pytest.fixture
def registry():
    """Create a tools registry instance"""
    return ToolsRegistry(
        llm_base_url="http://localhost:9000/v1",
        llm_api_key="test-key",
        ocr_base_url="http://localhost:8001"
    )


def test_registry_initialization(registry):
    """Test registry initializes with LLM and OCR tools"""
    assert len(registry.tools) == 2
    assert "llm_chat" in registry.tools
    assert "ocr_process" in registry.tools


def test_get_tool(registry):
    """Test retrieving a tool"""
    tool = registry.get_tool("llm_chat")
    assert tool is not None
    assert tool.name == "llm_chat"
    assert tool.endpoint == "http://localhost:9000/v1/chat/completions"


def test_get_tool_not_found(registry):
    """Test retrieving non-existent tool"""
    tool = registry.get_tool("nonexistent")
    assert tool is None


def test_list_tools(registry):
    """Test listing all tools"""
    tools = registry.list_tools()
    assert len(tools) == 2
    tool_names = [t["name"] for t in tools]
    assert "llm_chat" in tool_names
    assert "ocr_process" in tool_names
    assert all("description" in t for t in tools)
    assert all("input_schema" in t for t in tools)


def test_register_custom_tool(registry):
    """Test registering a custom tool"""
    custom_tool = ToolSchema(
        name="memory_search",
        description="Search memory graph",
        input_schema={"type": "object"},
        endpoint="http://localhost:8002/search",
        method="POST"
    )
    registry.register(custom_tool)
    assert len(registry.tools) == 3
    assert registry.get_tool("memory_search") is not None


@pytest.mark.asyncio
async def test_call_llm_tool():
    """Test calling LLM tool"""
    registry = ToolsRegistry(
        llm_base_url="http://localhost:9000/v1",
        llm_api_key="test-key",
        ocr_base_url="http://localhost:8001"
    )
    
    mock_response = {
        "id": "chatcmpl-123",
        "choices": [{"message": {"content": "Hello!"}}]
    }
    
    # Create mock response object with async json() method
    mock_resp = MagicMock()
    mock_resp.json = AsyncMock(return_value=mock_response)
    mock_resp.raise_for_status = MagicMock()
    
    # Create mock client
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await registry.call_tool(
            "llm_chat",
            messages=[{"role": "user", "content": "Hello"}]
        )
        
        assert result == mock_response


@pytest.mark.asyncio
async def test_call_ocr_tool():
    """Test calling OCR tool"""
    registry = ToolsRegistry(
        llm_base_url="http://localhost:9000/v1",
        llm_api_key="test-key",
        ocr_base_url="http://localhost:8001"
    )
    
    mock_response = {
        "text": "Extracted text from image",
        "confidence": 0.95
    }
    
    # Create mock response object with async json() method
    mock_resp = MagicMock()
    mock_resp.json = AsyncMock(return_value=mock_response)
    mock_resp.raise_for_status = MagicMock()
    
    # Create mock client
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await registry.call_tool(
            "ocr_process",
            image_path="/path/to/image.png"
        )
        
        assert result == mock_response


@pytest.mark.asyncio
async def test_call_tool_not_found():
    """Test calling non-existent tool"""
    registry = ToolsRegistry(
        llm_base_url="http://localhost:9000/v1",
        llm_api_key="test-key",
        ocr_base_url="http://localhost:8001"
    )
    
    with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
        await registry.call_tool("nonexistent", foo="bar")


@pytest.mark.asyncio
async def test_llm_tool_includes_auth_header():
    """Test LLM tool includes Authorization header"""
    registry = ToolsRegistry(
        llm_base_url="http://localhost:9000/v1",
        llm_api_key="secret-key-123",
        ocr_base_url="http://localhost:8001"
    )
    
    # Create mock response object with async json() method
    mock_resp = MagicMock()
    mock_resp.json = AsyncMock(return_value={})
    mock_resp.raise_for_status = MagicMock()
    
    # Create mock client
    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        await registry.call_tool("llm_chat", messages=[])
        
        # Verify auth header was set
        call_args = mock_client.request.call_args
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer secret-key-123"