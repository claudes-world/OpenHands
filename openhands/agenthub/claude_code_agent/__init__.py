"""Claude Code Agent for OpenHands.

This agent integrates Claude Code SDK with OpenHands, offering two modes:
1. Integrated mode: Maps Claude actions to OpenHands events for full tracking
2. Autonomous mode: Lets Claude Code run freely with progress streaming
"""

from openhands.agenthub.claude_code_agent.claude_code_agent import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
)
from openhands.controller.agent import Agent

# Register the agent with OpenHands
Agent.register("ClaudeCodeAgent", ClaudeCodeAgent)

__all__ = ["ClaudeCodeAgent", "ClaudeCodeAgentConfig"]