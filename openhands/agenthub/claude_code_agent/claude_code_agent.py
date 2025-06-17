"""Claude Code Agent - Hybrid integration of Claude Code SDK with OpenHands."""

import os
import json
from typing import Any, Dict, List, Optional

from openhands.controller.agent import Agent
from openhands.controller.state.state import State
from openhands.core.config.agent_config import AgentConfig
from openhands.core.logger import openhands_logger as logger
from openhands.events.action import (
    Action,
    AgentFinishAction,
    CmdRunAction,
    FileEditAction,
    FileReadAction,
    FileWriteAction,
    MessageAction,
)
from openhands.events.observation import (
    CmdOutputObservation,
    FileReadObservation,
    FileWriteObservation,
)
from openhands.llm.llm import LLM
from openhands.runtime.plugins import PluginRequirement


class ClaudeCodeAgentConfig(AgentConfig):
    """Configuration for Claude Code Agent."""
    
    mode: str = 'integrated'  # 'integrated' or 'autonomous'
    stream_progress: bool = True  # Stream progress updates in autonomous mode
    enable_web_search: bool = True
    enable_code_execution: bool = True
    

class ClaudeCodeAgent(Agent):
    """Agent that integrates Claude Code SDK with OpenHands.
    
    This agent supports two modes:
    1. 'integrated': Maps Claude Code actions to OpenHands events for full tracking
    2. 'autonomous': Lets Claude Code run freely with progress streaming
    """
    
    VERSION = '1.0'
    
    def __init__(self, llm: LLM, config: AgentConfig):
        super().__init__(llm, config)
        self.config: ClaudeCodeAgentConfig = config
        self.claude_session = None
        self._pending_actions: List[Action] = []
        
        # Initialize Claude Code SDK wrapper (to be implemented)
        try:
            from .claude_sdk_wrapper import ClaudeCodeSDKWrapper
            self.claude_wrapper = ClaudeCodeSDKWrapper(
                api_key=self.llm.config.api_key,
                model=self.llm.config.model,
            )
        except ImportError:
            logger.warning(
                "Claude Code SDK not installed. Please install with: "
                "pip install claude-code-sdk"
            )
            self.claude_wrapper = None
    
    def step(self, state: State) -> Action:
        """Execute one step of the agent.
        
        Args:
            state: Current state containing conversation history and context
            
        Returns:
            Action to be executed
        """
        # Check if we have pending actions from previous step
        if self._pending_actions:
            return self._pending_actions.pop(0)
        
        # Extract current task/message from state
        last_user_message = self._get_last_user_message(state)
        if not last_user_message:
            return MessageAction("I'm ready to help. What would you like me to do?")
        
        # Choose execution mode
        if self.config.mode == 'autonomous':
            return self._run_autonomous(state, last_user_message)
        else:
            return self._run_integrated(state, last_user_message)
    
    def _run_integrated(self, state: State, task: str) -> Action:
        """Run in integrated mode - full OpenHands event tracking."""
        if not self.claude_wrapper:
            return MessageAction(
                "Claude Code SDK is not available. Please install it first."
            )
        
        try:
            # Get Claude's next action
            claude_response = self.claude_wrapper.get_next_action(
                task=task,
                conversation_history=self._format_history(state),
                workspace_path=state.workspace_path,
            )
            
            # Convert Claude response to OpenHands action
            action = self._convert_claude_to_openhands_action(claude_response)
            
            # If Claude returns multiple actions, queue them
            if isinstance(action, list):
                self._pending_actions.extend(action[1:])
                return action[0]
            
            return action
            
        except Exception as e:
            logger.error(f"Error in integrated mode: {str(e)}")
            return MessageAction(f"Error executing Claude Code: {str(e)}")
    
    def _run_autonomous(self, state: State, task: str) -> Action:
        """Run in autonomous mode - let Claude Code handle everything."""
        if not self.claude_wrapper:
            return MessageAction(
                "Claude Code SDK is not available. Please install it first."
            )
        
        # Start message
        yield MessageAction("Starting Claude Code in autonomous mode...")
        
        try:
            # Create progress callback for streaming updates
            def on_progress(event: Dict[str, Any]):
                """Stream progress updates back to OpenHands UI."""
                event_type = event.get('type', 'unknown')
                
                if event_type == 'message':
                    self._pending_actions.append(
                        MessageAction(f"Claude: {event.get('content', '')}")
                    )
                elif event_type == 'file_created':
                    self._pending_actions.append(
                        MessageAction(f"Created file: {event.get('path', '')}")
                    )
                elif event_type == 'command_run':
                    self._pending_actions.append(
                        MessageAction(f"Running: {event.get('command', '')}")
                    )
                elif event_type == 'error':
                    self._pending_actions.append(
                        MessageAction(f"Error: {event.get('error', '')}")
                    )
            
            # Run Claude Code with progress callback
            result = self.claude_wrapper.run_autonomous(
                task=task,
                workspace_path=state.workspace_path,
                on_progress=on_progress if self.config.stream_progress else None,
            )
            
            # Add any pending progress messages
            while self._pending_actions:
                yield self._pending_actions.pop(0)
            
            # Return completion
            return AgentFinishAction(
                output=result.get('summary', 'Task completed successfully'),
                outputs={
                    'files_created': result.get('files_created', []),
                    'files_modified': result.get('files_modified', []),
                    'commands_run': result.get('commands_run', []),
                    'full_result': result,
                }
            )
            
        except Exception as e:
            logger.error(f"Error in autonomous mode: {str(e)}")
            return MessageAction(f"Error in autonomous execution: {str(e)}")
    
    def _convert_claude_to_openhands_action(
        self, claude_response: Dict[str, Any]
    ) -> Action:
        """Convert Claude Code SDK response to OpenHands action."""
        action_type = claude_response.get('action_type')
        
        if action_type == 'file_write':
            return FileWriteAction(
                path=claude_response['path'],
                content=claude_response['content'],
            )
        elif action_type == 'file_edit':
            return FileEditAction(
                path=claude_response['path'],
                old_str=claude_response.get('old_content', ''),
                new_str=claude_response.get('new_content', ''),
            )
        elif action_type == 'file_read':
            return FileReadAction(path=claude_response['path'])
        elif action_type == 'command':
            return CmdRunAction(command=claude_response['command'])
        elif action_type == 'message':
            return MessageAction(content=claude_response['content'])
        elif action_type == 'finish':
            return AgentFinishAction(output=claude_response.get('message', 'Done'))
        else:
            # Unknown action type, return as message
            return MessageAction(
                f"Claude performed action: {json.dumps(claude_response, indent=2)}"
            )
    
    def _get_last_user_message(self, state: State) -> Optional[str]:
        """Extract the last user message from state."""
        for event in reversed(state.history.get_events()):
            if event.source == 'user' and hasattr(event, 'content'):
                return event.content
        return None
    
    def _format_history(self, state: State) -> List[Dict[str, str]]:
        """Format conversation history for Claude Code SDK."""
        messages = []
        for event in state.history.get_events():
            if hasattr(event, 'content'):
                messages.append({
                    'role': 'user' if event.source == 'user' else 'assistant',
                    'content': event.content,
                })
        return messages
    
    def reset(self) -> None:
        """Reset the agent state."""
        super().reset()
        self._pending_actions.clear()
        if self.claude_session:
            # Clean up any active Claude session
            try:
                self.claude_wrapper.close_session(self.claude_session)
            except:
                pass
            self.claude_session = None
    
    def get_agent_config_class(self) -> type[AgentConfig]:
        """Return the configuration class for this agent."""
        return ClaudeCodeAgentConfig
    
    @property
    def sandbox_plugins(self) -> List[PluginRequirement]:
        """Return required plugins for the sandbox."""
        return []