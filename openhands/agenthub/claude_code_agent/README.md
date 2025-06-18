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
- Python 3.10+
- Node.js (for Claude Code CLI)
- Valid Anthropic API key

## Installation

1. Install the Claude Code CLI (required by the SDK):
```bash
npm install -g @anthropic-ai/claude-code
```

2. Install the Python SDK:
```bash
pip install claude-code-sdk
```

3. Set your Anthropic API key:
```bash
export ANTHROPIC_API_KEY=your_api_key_here
```

The agent is automatically registered when OpenHands starts.

## Example

```python
# The agent will be available in the UI agent selector
# Or via CLI:
openhands --agent ClaudeCodeAgent --task "Create a Python web scraper"
```

## How It Works

The Claude Code Agent uses the official Claude Code SDK, which:
- Requires the Claude Code CLI to be installed
- Streams messages asynchronously
- Provides built-in tools (Read, Write, Bash)
- Supports both integrated and autonomous modes

In **integrated mode**, each tool use is converted to an OpenHands event for full tracking.
In **autonomous mode**, Claude completes the entire task with progress streaming.