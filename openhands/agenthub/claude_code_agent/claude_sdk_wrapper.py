"""Wrapper for Claude Code SDK integration with OpenHands."""

import asyncio
import os
from typing import Any, AsyncIterator, Callable, Optional

from openhands.core.logger import openhands_logger as logger

try:
    from claude_code_sdk import (
        AssistantMessage,
        ClaudeCodeOptions,
        SystemMessage,
        TextBlock,
        ToolUseBlock,
        query,
    )

    CLAUDE_SDK_AVAILABLE = True
except ImportError:
    CLAUDE_SDK_AVAILABLE = False
    logger.warning(
        'Claude Code SDK not found. Please install with: pip install claude-code-sdk'
    )


class ClaudeCodeSDKWrapper:
    """Wrapper around Claude Code SDK to integrate with OpenHands.

    This wrapper handles:
    1. Async-to-sync bridge for OpenHands compatibility
    2. Message stream parsing to extract actions
    3. Tool use tracking and conversion
    """

    def __init__(self, api_key: str, model: str = 'claude-3-5-sonnet-20241022'):
        """Initialize the Claude Code SDK wrapper.

        Args:
            api_key: Anthropic API key
            model: Model to use (default: claude-3-5-sonnet)
        """
        if not CLAUDE_SDK_AVAILABLE:
            raise ImportError(
                'Claude Code SDK not found. Please install with:\n'
                '1. pip install claude-code-sdk\n'
                '2. npm install -g @anthropic-ai/claude-code'
            )

        self.api_key = api_key
        self.model = model

        # Set API key in environment for Claude Code CLI
        os.environ['ANTHROPIC_API_KEY'] = api_key

        logger.info(f'Claude Code SDK wrapper initialized with model: {model}')

    async def _query_claude(
        self,
        prompt: str,
        options: Optional[ClaudeCodeOptions] = None,
    ) -> AsyncIterator[Any]:
        """Internal async method to query Claude Code SDK."""
        async for message in query(prompt, options):
            yield message

    def get_next_action(
        self,
        task: str,
        conversation_history: list[dict[str, str]],
        workspace_path: str,
    ) -> dict[str, Any]:
        """Get the next action from Claude Code in integrated mode.

        This runs Claude for a single "turn" and extracts the first action.

        Args:
            task: Current task/instruction
            conversation_history: Previous conversation messages
            workspace_path: Path to the workspace directory

        Returns:
            Dictionary with action details
        """
        # Configure options for integrated mode
        options = ClaudeCodeOptions(
            allowed_tools=['Read', 'Write', 'Bash'],
            cwd=workspace_path,
            model=self.model,
            max_turns=1,  # Only one turn in integrated mode
            permission_mode='default',  # We'll handle permissions in OpenHands
        )

        # Build prompt from conversation history
        prompt = self._build_prompt(task, conversation_history)

        # Run async query synchronously
        action = asyncio.run(self._get_single_action(prompt, options))

        return action

    async def _get_single_action(
        self, prompt: str, options: ClaudeCodeOptions
    ) -> dict[str, Any]:
        """Extract a single action from Claude's response."""
        collected_messages = []

        async for message in self._query_claude(prompt, options):
            collected_messages.append(message)

            # Look for tool use in assistant messages
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        # Found a tool use, convert and return it
                        return self._convert_tool_use_to_action(block)
                    elif isinstance(block, TextBlock) and block.text.strip():
                        # If there's text but no tool use, return as message
                        return {
                            'action_type': 'message',
                            'content': block.text,
                        }

        # If we get here, no action was found
        return {
            'action_type': 'message',
            'content': 'I need more information to proceed with this task.',
        }

    def _convert_tool_use_to_action(self, tool_use: ToolUseBlock) -> dict[str, Any]:
        """Convert Claude Code SDK tool use to OpenHands action format."""
        tool_name = tool_use.name
        tool_input = tool_use.input

        if tool_name == 'Write':
            return {
                'action_type': 'file_write',
                'path': tool_input.get('path', ''),
                'content': tool_input.get('content', ''),
            }
        elif tool_name == 'Read':
            return {
                'action_type': 'file_read',
                'path': tool_input.get('path', ''),
            }
        elif tool_name == 'Bash':
            return {
                'action_type': 'command',
                'command': tool_input.get('command', ''),
            }
        else:
            # Unknown tool, return as message
            return {
                'action_type': 'message',
                'content': f'Used tool: {tool_name} with input: {tool_input}',
            }

    def _build_prompt(
        self, task: str, conversation_history: list[dict[str, str]]
    ) -> str:
        """Build a prompt from task and conversation history."""
        # Start with the task
        prompt = task

        # Add relevant context from history if needed
        if conversation_history:
            # Include last few messages for context
            recent_messages = conversation_history[-3:]
            if recent_messages:
                prompt = 'Previous context:\n'
                for msg in recent_messages:
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    prompt += f'{role}: {content}\n'
                prompt += f'\nCurrent task: {task}'

        return prompt

    def run_autonomous(
        self,
        task: str,
        workspace_path: str,
        on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        """Run Claude Code in autonomous mode.

        Args:
            task: Task to complete
            workspace_path: Path to the workspace directory
            on_progress: Optional callback for progress updates

        Returns:
            Dictionary with execution results
        """
        logger.info(f'Running autonomous mode for task: {task}')

        # Configure options for autonomous mode
        options = ClaudeCodeOptions(
            allowed_tools=['Read', 'Write', 'Bash'],
            cwd=workspace_path,
            model=self.model,
            max_turns=None,  # Let Claude work until completion
            permission_mode='acceptEdits',  # Auto-accept edits in autonomous mode
        )

        # Run async query synchronously
        result = asyncio.run(self._run_autonomous_async(task, options, on_progress))

        return result

    async def _run_autonomous_async(
        self,
        task: str,
        options: ClaudeCodeOptions,
        on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
    ) -> dict[str, Any]:
        """Async implementation of autonomous mode."""
        files_created: list[str] = []
        files_modified: list[str] = []
        commands_run: list[str] = []
        all_messages = []

        try:
            async for message in self._query_claude(task, options):
                all_messages.append(message)

                # Process different message types
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and on_progress:
                            # Stream text updates
                            on_progress(
                                {
                                    'type': 'message',
                                    'content': block.text,
                                }
                            )
                        elif isinstance(block, ToolUseBlock):
                            # Track tool uses
                            tool_event = self._process_tool_use(
                                block, files_created, files_modified, commands_run
                            )
                            if on_progress and tool_event:
                                on_progress(tool_event)

                elif isinstance(message, SystemMessage) and on_progress:
                    # System messages might contain important info
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            on_progress(
                                {
                                    'type': 'system',
                                    'content': block.text,
                                }
                            )

            # Build summary
            summary = self._build_summary(all_messages)

            return {
                'success': True,
                'summary': summary,
                'files_created': files_created,
                'files_modified': files_modified,
                'commands_run': commands_run,
                'messages': len(all_messages),
            }

        except Exception as e:
            logger.error(f'Error in autonomous mode: {str(e)}')
            return {
                'success': False,
                'summary': f'Error: {str(e)}',
                'files_created': files_created,
                'files_modified': files_modified,
                'commands_run': commands_run,
                'error': str(e),
            }

    def _process_tool_use(
        self,
        tool_use: ToolUseBlock,
        files_created: list[str],
        files_modified: list[str],
        commands_run: list[str],
    ) -> Optional[dict[str, Any]]:
        """Process a tool use and update tracking lists."""
        tool_name = tool_use.name
        tool_input = tool_use.input

        if tool_name == 'Write':
            path = tool_input.get('path', '')
            if path:
                # Check if file exists (simplified check)
                if path not in files_created:
                    files_created.append(path)
                else:
                    if path not in files_modified:
                        files_modified.append(path)

                return {
                    'type': 'file_created'
                    if path in files_created
                    else 'file_modified',
                    'path': path,
                }

        elif tool_name == 'Bash':
            command = tool_input.get('command', '')
            if command:
                commands_run.append(command)
                return {
                    'type': 'command_run',
                    'command': command,
                }

        return None

    def _build_summary(self, messages: list[Any]) -> str:
        """Build a summary from all messages."""
        # Look for the last assistant message with meaningful content
        for message in reversed(messages):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock) and block.text.strip():
                        # Use the last meaningful text as summary
                        return block.text.strip()

        return 'Task completed successfully.'
