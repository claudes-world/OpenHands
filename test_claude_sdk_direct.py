#!/usr/bin/env python3
"""Direct test of Claude Code SDK"""

import asyncio
import os

# Test if we can import the SDK
try:
    from claude_code_sdk import ClaudeCodeOptions, query

    print('✅ Claude Code SDK imported successfully!')
except ImportError as e:
    print(f'❌ Failed to import Claude Code SDK: {e}')
    print('Please install: pip install claude-code-sdk')
    exit(1)

# Check API key
if not os.environ.get('ANTHROPIC_API_KEY'):
    print('❌ Please set ANTHROPIC_API_KEY environment variable')
    exit(1)


async def test_claude_code():
    """Test Claude Code SDK directly"""
    print('\n🚀 Testing Claude Code SDK...')

    # Configure options
    options = ClaudeCodeOptions(
        allowed_tools=['Read', 'Write', 'Bash'],
        cwd='./test_workspace',
        max_turns=1,
    )

    # Simple test prompt
    prompt = "Create a file called hello.py that prints 'Hello from Claude Code SDK!'"

    print(f'📝 Prompt: {prompt}')
    print('🔧 Running Claude Code...')

    messages = []
    async for message in query(prompt, options):
        messages.append(message)
        print(f'📨 Received: {type(message).__name__}')

        # Print content if it's a text message
        if hasattr(message, 'content'):
            for block in message.content:
                if hasattr(block, 'text'):
                    print(f'   Text: {block.text}')
                elif hasattr(block, 'name'):
                    print(f'   Tool: {block.name}')

    print(f'\n✅ Received {len(messages)} messages')

    # Check if file was created
    test_file = './test_workspace/hello.py'
    if os.path.exists(test_file):
        print(f'✅ File created: {test_file}')
        with open(test_file, 'r') as f:
            print(f'📄 Content:\n{f.read()}')
    else:
        print('❌ File was not created')


if __name__ == '__main__':
    # Create test workspace
    os.makedirs('test_workspace', exist_ok=True)

    # Run the test
    asyncio.run(test_claude_code())
