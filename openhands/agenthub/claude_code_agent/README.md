# Claude Code Agent

The Claude Code Agent integrates the Claude Code SDK with OpenHands, providing a powerful hybrid approach to AI-assisted software development.

## Features

- **Dual Mode Operation**:
  - **Integrated Mode**: Full OpenHands event tracking and granular control
  - **Autonomous Mode**: Let Claude Code work freely with progress streaming

- **Complete Tool Integration**: File operations, command execution, web search, and more
- **Progress Streaming**: Real-time updates in autonomous mode
- **Sandboxed Execution**: All operations run safely in Docker containers

## Configuration

The agent can be configured in your `config.toml`:

```toml
[agent]
default_agent = "ClaudeCodeAgent"

[agent.ClaudeCodeAgent]
mode = "integrated"  # or "autonomous"
stream_progress = true
enable_web_search = true
enable_code_execution = true
```

## Usage

### Integrated Mode

In integrated mode, the agent maps each Claude Code action to an OpenHands event, providing:
- Full audit trail of every action
- Ability to pause/resume execution
- Detailed cost tracking
- Step-by-step visibility

### Autonomous Mode

In autonomous mode, Claude Code runs more freely:
- Better performance for complex tasks
- Natural Claude Code optimizations
- Progress updates streamed to UI
- Summary of accomplishments at completion

## Requirements

- OpenHands installation
- Claude Code SDK (when available)
- Valid Anthropic API key

## Installation

The agent is automatically registered when OpenHands starts. Once the Claude Code SDK is released, install it with:

```bash
pip install claude-code-sdk
```

## Example

```python
# The agent will be available in the UI agent selector
# Or via CLI:
openhands --agent ClaudeCodeAgent --task "Create a Python web scraper"
```

## Development Status

Currently includes a mock implementation for testing. The full implementation will be activated once the Claude Code SDK is publicly available.