---
name: python-tests
description: Run focused Python tests and interpret actual failures.
triggers: ["运行测试", "单元测试", "run python tests"]
---
# Focused Python testing workflow

Read the implementation and related tests before selecting a command. The task is to verify behavior, not to produce a green indicator at any cost. Preserve all existing expectations unless the user explicitly changes the contract. A test runner failure and an assertion failure require different diagnoses.

1. Locate a related test file, usually test_<module>.py beside the module or under tests/. Prefer this scope before running an unrelated full suite. If the project documents a different runner in AGENTS.md or its package configuration, follow that documented command.
2. Use the existing read tool to open skill://python-tests/scripts/run_tests.py when the helper is useful. The returned package_file is the actual local application script path. In Agent or Debug mode it can be executed with the bundled Python and a --workspace and --pattern argument; this adds no new model tool. Do not copy a helper into user files unless requested.
3. Reproduce the original failure and capture the real exit code, stdout and stderr. Python unittest normally writes progress to stderr. On Windows avoid combining 2>&1 with an ErrorActionPreference that converts normal stderr into a terminating PowerShell error. Preserve the native process exit code.
4. For a code fix, make the smallest unique edit and rerun the same focused cases. Include ordinary, empty and invalid inputs when these are part of the actual contract. The post-edit hook may also run related tests; use its returned result rather than guessing whether it passed.
5. An absent dependency, missing interpreter or test discovery error is an incomplete verification. Do not silently skip it. Install project dependencies only within the project-specific dependency location and within the user's task scope.
6. Summarize the exact cases executed, their result and any remaining limitation. Never turn a failing assertion into a passing one by weakening the expected value. Do not claim a complete regression suite was run when only one file was selected.

Ask and Plan modes may explain a test or produce a plan but cannot execute this script. Safety hooks still gate shell commands. The helper accepts a bounded test pattern and does not itself change application code; project test code still executes with the current user's permissions.
