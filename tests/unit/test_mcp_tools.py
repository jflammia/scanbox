"""Unit tests for MCP server tools registration."""

from scanbox.mcp.server import mcp


class TestMCPToolRegistration:
    def test_server_has_name(self):
        assert mcp.name == "scanbox"

    def test_health_check_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_health_check" in tools

    def test_manage_persons_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_manage_persons" in tools

    def test_create_session_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_create_session" in tools

    def test_list_sessions_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_list_sessions" in tools

    def test_get_batch_status_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_get_batch_status" in tools

    def test_list_documents_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_list_documents" in tools

    def test_get_document_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_get_document" in tools

    def test_update_document_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_update_document" in tools

    def test_save_batch_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_save_batch" in tools

    def test_scan_fronts_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_scan_fronts" in tools

    def test_scan_backs_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_scan_backs" in tools

    def test_skip_backs_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_skip_backs" in tools

    def test_adjust_boundaries_tool_registered(self):
        tools = mcp._tool_manager._tools
        assert "scanbox_adjust_boundaries" in tools
