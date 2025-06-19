# Claude Code Agent Implementation Notes

## Key Differences from Initial Design

When we first designed the Claude Code Agent, we made assumptions about how the SDK would work. The actual Claude Code SDK works quite differently:

### Initial Assumptions
- Direct API client with synchronous methods
- Returns discrete actions
- Session-based with explicit session management

### Actual SDK Behavior
- Requires the Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- Async-first with streaming responses
- Uses an async generator pattern (`async for message in query(...)`)
- Built-in tools (Read, Write, Bash) that Claude uses directly
- No explicit session management - each query is independent

## Architecture Decisions

### Async-to-Sync Bridge
Since OpenHands agents use synchronous `step()` methods, we use `asyncio.run()` to bridge the gap:
```python
action = asyncio.run(self._get_single_action(prompt, options))
```

### Two Modes of Operation

#### Integrated Mode
- Runs Claude for a single turn (`max_turns=1`)
- Extracts the first tool use or message
- Converts to OpenHands actions
- Full event tracking and granular control

#### Autonomous Mode
- Lets Claude run to completion (`max_turns=None`)
- Streams progress updates via callback
- Returns summary when complete
- Better performance for complex tasks

### Message Parsing
The SDK returns messages with content blocks:
- `TextBlock`: Regular text messages
- `ToolUseBlock`: When Claude uses a tool (Read, Write, Bash)
- `ToolResultBlock`: Results from tool execution

We parse these to extract actions and convert them to OpenHands format.

## Future Improvements

1. **Persistent Sessions**: The SDK might support session continuity in the future
2. **More Tools**: Additional tools beyond Read, Write, Bash
3. **Better Error Handling**: More specific error types and recovery
4. **Performance**: Optimize the async-to-sync bridge
5. **Streaming in Integrated Mode**: Stream partial results even in integrated mode

## Testing Considerations

- The SDK requires both Python package and Node.js CLI
- Mock the SDK wrapper in tests to avoid CLI dependency
- Test both modes thoroughly
- Verify tool use parsing works correctly
- Handle edge cases (no response, errors, timeouts)