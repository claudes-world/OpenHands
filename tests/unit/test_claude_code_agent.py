"""Unit tests for Claude Code Agent."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from openhands.agenthub.claude_code_agent.claude_code_agent import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
)
from openhands.controller.state.state import State
from openhands.events.action import (
    MessageAction,
    FileWriteAction,
    CmdRunAction,
    AgentFinishAction,
)
from openhands.events.event import Event
from openhands.llm.llm import LLM


class TestClaudeCodeAgent:
    """Test cases for Claude Code Agent."""
    
    @pytest.fixture
    def mock_llm(self):
        """Create a mock LLM."""
        llm = Mock(spec=LLM)
        llm.config = Mock()
        llm.config.api_key = "test-api-key"
        llm.config.model = "claude-3-5-sonnet"
        return llm
    
    @pytest.fixture
    def mock_state(self):
        """Create a mock state."""
        state = Mock(spec=State)
        state.workspace_path = "/test/workspace"
        state.history = Mock()
        state.history.get_events = Mock(return_value=[])
        return state
    
    @pytest.fixture
    def integrated_agent(self, mock_llm):
        """Create an agent in integrated mode."""
        config = ClaudeCodeAgentConfig(mode='integrated')
        # Patch the import to avoid ImportError in tests
        with patch('openhands.agenthub.claude_code_agent.claude_code_agent.ClaudeCodeSDKWrapper'):
            agent = ClaudeCodeAgent(mock_llm, config)
            agent.claude_wrapper = Mock()
        return agent
    
    @pytest.fixture
    def autonomous_agent(self, mock_llm):
        """Create an agent in autonomous mode."""
        config = ClaudeCodeAgentConfig(mode='autonomous')
        with patch('openhands.agenthub.claude_code_agent.claude_code_agent.ClaudeCodeSDKWrapper'):
            agent = ClaudeCodeAgent(mock_llm, config)
            agent.claude_wrapper = Mock()
        return agent
    
    def test_agent_initialization(self, mock_llm):
        """Test agent can be initialized with different modes."""
        # Test integrated mode
        config = ClaudeCodeAgentConfig(mode='integrated')
        with patch('openhands.agenthub.claude_code_agent.claude_code_agent.ClaudeCodeSDKWrapper'):
            agent = ClaudeCodeAgent(mock_llm, config)
        assert agent.config.mode == 'integrated'
        
        # Test autonomous mode
        config = ClaudeCodeAgentConfig(mode='autonomous')
        with patch('openhands.agenthub.claude_code_agent.claude_code_agent.ClaudeCodeSDKWrapper'):
            agent = ClaudeCodeAgent(mock_llm, config)
        assert agent.config.mode == 'autonomous'
    
    def test_step_with_no_user_message(self, integrated_agent, mock_state):
        """Test step returns greeting when no user message."""
        action = integrated_agent.step(mock_state)
        assert isinstance(action, MessageAction)
        assert "ready to help" in action.content.lower()
    
    def test_integrated_mode_file_write(self, integrated_agent, mock_state):
        """Test integrated mode converts file write correctly."""
        # Mock user message
        user_event = Mock()
        user_event.source = 'user'
        user_event.content = 'Create a test file'
        mock_state.history.get_events.return_value = [user_event]
        
        # Mock Claude response
        integrated_agent.claude_wrapper.get_next_action.return_value = {
            'action_type': 'file_write',
            'path': 'test.py',
            'content': 'print("Hello")',
        }
        
        action = integrated_agent.step(mock_state)
        assert isinstance(action, FileWriteAction)
        assert action.path == 'test.py'
        assert action.content == 'print("Hello")'
    
    def test_integrated_mode_command_run(self, integrated_agent, mock_state):
        """Test integrated mode converts command run correctly."""
        # Mock user message
        user_event = Mock()
        user_event.source = 'user'
        user_event.content = 'Run python --version'
        mock_state.history.get_events.return_value = [user_event]
        
        # Mock Claude response
        integrated_agent.claude_wrapper.get_next_action.return_value = {
            'action_type': 'command',
            'command': 'python --version',
        }
        
        action = integrated_agent.step(mock_state)
        assert isinstance(action, CmdRunAction)
        assert action.command == 'python --version'
    
    def test_autonomous_mode_completion(self, autonomous_agent, mock_state):
        """Test autonomous mode returns completion action."""
        # Mock user message
        user_event = Mock()
        user_event.source = 'user'
        user_event.content = 'Build a web scraper'
        mock_state.history.get_events.return_value = [user_event]
        
        # Mock Claude autonomous response
        autonomous_agent.claude_wrapper.run_autonomous.return_value = {
            'success': True,
            'summary': 'Created web scraper successfully',
            'files_created': ['scraper.py'],
            'commands_run': ['pip install requests'],
        }
        
        action = autonomous_agent.step(mock_state)
        assert isinstance(action, AgentFinishAction)
        assert 'successfully' in action.output
    
    def test_convert_action_types(self, integrated_agent):
        """Test conversion of various Claude action types."""
        # Test message action
        action = integrated_agent._convert_claude_to_openhands_action({
            'action_type': 'message',
            'content': 'Test message',
        })
        assert isinstance(action, MessageAction)
        assert action.content == 'Test message'
        
        # Test finish action
        action = integrated_agent._convert_claude_to_openhands_action({
            'action_type': 'finish',
            'message': 'Task completed',
        })
        assert isinstance(action, AgentFinishAction)
        assert action.output == 'Task completed'
        
        # Test unknown action type
        action = integrated_agent._convert_claude_to_openhands_action({
            'action_type': 'unknown',
            'data': 'test',
        })
        assert isinstance(action, MessageAction)
        assert 'Claude performed action' in action.content
    
    def test_get_last_user_message(self, integrated_agent, mock_state):
        """Test extraction of last user message from state."""
        # Create mock events
        events = [
            Mock(source='system', content='System message'),
            Mock(source='user', content='First user message'),
            Mock(source='assistant', content='Assistant response'),
            Mock(source='user', content='Last user message'),
        ]
        mock_state.history.get_events.return_value = events
        
        last_message = integrated_agent._get_last_user_message(mock_state)
        assert last_message == 'Last user message'
    
    def test_reset_clears_state(self, integrated_agent):
        """Test reset clears pending actions and session."""
        # Add some pending actions
        integrated_agent._pending_actions = [
            MessageAction("pending1"),
            MessageAction("pending2"),
        ]
        integrated_agent.claude_session = Mock()
        
        integrated_agent.reset()
        
        assert len(integrated_agent._pending_actions) == 0
        assert integrated_agent.claude_session is None