#!/usr/bin/env python3
"""Test Claude CLI directly to validate our integration approach"""

import json
import os
import subprocess


def test_claude_cli():
    """Test Claude CLI directly with a simple task"""
    print('🚀 Testing Claude CLI directly...')

    # Create test workspace
    os.makedirs('test_workspace', exist_ok=True)

    # Test prompt
    prompt = (
        "Create a file called test_output.py that prints 'Hello from Claude CLI test!'"
    )

    print(f'📝 Prompt: {prompt}')

    try:
        # Run Claude with --print for non-interactive output
        result = subprocess.run(
            ['claude', '--print', '--output-format', 'json', prompt],
            capture_output=True,
            text=True,
            cwd='test_workspace',
        )

        if result.returncode == 0:
            print('✅ Claude CLI executed successfully!')

            # Try to parse JSON output
            try:
                output = json.loads(result.stdout)
                print(f'📄 Response type: {output.get("type", "unknown")}')
                if 'content' in output:
                    print(f'📝 Content: {output["content"][:200]}...')
            except json.JSONDecodeError:
                print(f'📝 Text output: {result.stdout[:200]}...')

            # Check if any files were created
            files = os.listdir('test_workspace')
            if files:
                print(f'📁 Files created: {files}')

                # Read any Python files
                for file in files:
                    if file.endswith('.py'):
                        with open(f'test_workspace/{file}', 'r') as f:
                            print(f'📄 {file} content:\n{f.read()}')
            else:
                print('📁 No files created')

        else:
            print(f'❌ Claude CLI failed with return code: {result.returncode}')
            print(f'Error: {result.stderr}')

    except FileNotFoundError:
        print("❌ Claude CLI not found. Make sure it's installed and in PATH.")
    except Exception as e:
        print(f'❌ Error running Claude CLI: {e}')


def test_claude_interactive_simulation():
    """Simulate how our OpenHands agent would interact with Claude"""
    print('\n🔄 Testing interactive simulation...')

    tasks = [
        'Create a file called hello.py with a simple hello world program',
        'List the files in the current directory',
        'Run the hello.py file',
    ]

    for i, task in enumerate(tasks, 1):
        print(f'\n📝 Task {i}: {task}')

        try:
            result = subprocess.run(
                ['claude', '--print', task],
                capture_output=True,
                text=True,
                cwd='test_workspace',
                timeout=30,
            )

            if result.returncode == 0:
                print(f'✅ Task {i} completed')
                print(f'📝 Response: {result.stdout[:150]}...')
            else:
                print(f'❌ Task {i} failed: {result.stderr}')

        except subprocess.TimeoutExpired:
            print(f'⏱️ Task {i} timed out')
        except Exception as e:
            print(f'❌ Task {i} error: {e}')


if __name__ == '__main__':
    test_claude_cli()
    test_claude_interactive_simulation()

    print('\n🎯 This demonstrates how our Claude Code Agent would work:')
    print('1. Send prompts to Claude CLI')
    print('2. Parse responses and extract actions')
    print('3. Convert to OpenHands action format')
    print('4. Handle file operations and command execution')
