# 原始 Git 提交索引

应用构建基线：`b2952d1a378238f9afa4d06929a446a0575b4fe2`。日期保留 Git 原始的北京时间，索引共 27 次提交，未包含之后补充日志的文档提交。

2026-10-27 的需求及本地工作见 [开发日志](../development-log.md)；该日没有本仓库 Git 提交。机器可读数据见 [commits.json](commits.json)。

## 2026-10-29 · 23 次提交

- 11:52:07 · [951301c](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/951301c469aeaa73b7014bc46f165ee0e089466d) · build: pin application dependencies and exclude local secrets
  变更文件：`.env.example`、`.gitignore`、`pyproject.toml`、`requirements-lock.txt`。
- 11:52:08 · [d2b1b58](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/d2b1b580ff8c0b485e9a157148fec97ca47f5c67) · feat: implement exact file tools and persistent conflict-safe undo
  变更文件：`agent/__init__.py`、`agent/changes.py`、`agent/tools.py`、`tests/test_tools.py`。
- 11:52:08 · [67fd616](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/67fd6162114f762a7f30a6b32756b7ef4695f99d) · feat: configure providers and Windows credential storage
  变更文件：`agent/settings.py`、`tests/test_settings.py`。
- 11:52:08 · [d204aec](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/d204aec3673d412c758284009fa66f2d8e969e0d) · feat: stream compatible model replies with completion validation
  变更文件：`agent/provider.py`、`tests/test_provider.py`。
- 11:52:08 · [972c2ff](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/972c2ffebc13899d23bf3b94a6ffcfb3feec7ea5) · feat: integrate external MCP servers and bundled demonstration service
  变更文件：`agent/mcp_client.py`、`mcp.json`、`mcp_demo.py`。
- 11:52:09 · [ecf8bfe](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/ecf8bfe12216caa1209c96d4a1009368e08ba5b6) · feat: add bounded agent loop with cancellation and context management
  变更文件：`agent/runtime.py`、`tests/test_runtime.py`。
- 11:52:09 · [96d378b](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/96d378baea48ce487cfabd8b06338c3d7cecb321) · feat: expose authenticated local REST WebSocket and SSE endpoints
  变更文件：`server/__init__.py`、`server/app.py`、`tests/test_server.py`。
- 11:52:09 · [a41d02c](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/a41d02c1de19fa70775631b858b5c06cbd72f578) · feat: add desktop workspace model settings and visible tool interaction
  变更文件：`ui/app.js`、`ui/index.html`、`ui/style.css`。
- 11:52:09 · [082c2aa](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/082c2aa3ade60c3b61666e6ceee77a964a452826) · feat: launch native desktop window with independent backend mode
  变更文件：`app.py`。
- 11:52:10 · [8958679](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/89586792703b606589307313601f7a32eee721a8) · docs: include an isolated first-run example project
  变更文件：`sample_workspace/README.md`、`sample_workspace/stats.py`、`sample_workspace/test_stats.py`。
- 11:52:10 · [6488af8](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/6488af878fc3de2912b9720a92eb8563c2f4a8e7) · build: package Windows application MCP helper and installer
  变更文件：`scripts/build_windows.py`、`scripts/installer.iss`。
- 11:52:10 · [0448e7e](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0448e7ed164eb639c3bbfb313383ced48fc4f133) · ci: run Windows regression checks and document license
  变更文件：`.github/workflows/ci.yml`、`LICENSE`。
- 11:52:10 · [aca724e](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/aca724e6dbd4fdce4127b973ce4830824422cbb6) · docs: write complete setup usage and architectural report
  变更文件：`README.md`、`docs/build.md`、`report.md`。
- 11:52:11 · [8eeaa5e](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/8eeaa5ec2fde1144e7b509752eab6fd4c2c6b941) · docs: add verified screenshots and actual tool recovery trace
  变更文件：`docs/screenshots/01-main.png`、`docs/screenshots/02-settings.png`、`docs/screenshots/03-tools.png`、`docs/trace.md`、`docs/validation.md`。
- 11:52:11 · [de01204](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/de01204c70e303e0fe5fe95093e26b51438c70d8) · release: provide demonstration guide release notes and GitHub publishing script
  变更文件：`docs/demo-guide.md`、`docs/release-notes.md`、`scripts/publish_github.ps1`。
- 12:02:10 · [3ce8a91](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/3ce8a91429176ed57dcdb0f442c5449c3db75c1c) · test: verify packaged desktop MCP and undo API and record release evidence
  变更文件：`.github/workflows/ci.yml`、`README.md`、`demo.mp4`、`docs/demo-guide.md`、`docs/release-notes.md`、`docs/screenshots/01-main.png`、`docs/screenshots/02-settings.png`、`docs/screenshots/03-tools.png` 等 10 个文件，完整路径见 JSON。
- 12:07:49 · [4abe8d9](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/4abe8d998e3c2a33c20a004a6b5217c04cdb3bb4) · docs: record final 42-test pass and distribution acceptance boundaries
  变更文件：`docs/validation.md`。
- 12:46:41 · [0500e9f](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0500e9fcd4d2b2b5b0dddfef61a8f944af3d0f42) · Gate Windows releases on full signing and installation acceptance
  变更文件：`.gitignore`、`README.md`、`agent/mcp_client.py`、`docs/build.md`、`docs/release-notes.md`、`docs/signed-release-notes.md`、`docs/signing.md`、`docs/validation.md` 等 17 个文件，完整路径见 JSON。
- 16:47:32 · [0c142a0](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/0c142a0ef34bbc54d89d3a8330f3e20874ee6bb6) · Build 1.1 workbench with real online Q&A, editor modes and runtime distribution
  变更文件：`.github/workflows/ci.yml`、`.gitignore`、`README.md`、`agent/documents.py`、`agent/mcp_client.py`、`agent/modes.py`、`agent/network_guidance.py`、`agent/runtime.py` 等 46 个文件，完整路径见 JSON。
- 16:59:02 · [ae3f4b8](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/ae3f4b87689ad3d1611eab3f533265a69f84ca29) · Verify real API repair and polish resizable desktop delivery
  变更文件：`docs/real-api-debug-trace.md`、`docs/screenshots/01-main.png`、`docs/screenshots/02-settings.png`、`docs/screenshots/03-tools.png`、`docs/screenshots/04-qa.png`、`docs/validation.md`、`frontend/build.mjs`、`frontend/main.js` 等 12 个文件，完整路径见 JSON。
- 17:03:07 · [f79ef1f](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/f79ef1fbf05018c3d16f7d33c9c306e2c5176b5f) · Refresh delivery video and signing instructions
  变更文件：`demo.mp4`、`docs/demo-guide.md`、`docs/signing.md`。
- 17:10:19 · [74da197](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/74da1979a157f452ae50a96be793bc3ebb030398) · Fix Windows editor tab paths and finalize hand-in evidence
  变更文件：`demo.mp4`、`docs/demo-guide.md`、`docs/screenshots/01-main.png`、`docs/screenshots/02-settings.png`、`docs/screenshots/03-tools.png`、`docs/screenshots/04-qa.png`、`docs/validation.md`、`frontend/main.js` 等 14 个文件，完整路径见 JSON。
- 17:26:27 · [a9966f6](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/a9966f613115a4ad15ebe560807c4bf65e41d3c0) · Publish validated preview packages directly from Windows CI artifacts
  变更文件：`.github/workflows/preview-release.yml`。

## 2026-11-03 · 4 次提交

- 18:48:14 · [982dba6](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/982dba64762ea48d7c1e5d7cc08b01e6f4641a9f) · Add skills, customization hooks, durable jobs and authenticated MCP port
  变更文件：`.github/workflows/ci.yml`、`.github/workflows/preview-release.yml`、`AGENTS.md`、`README.md`、`agent/capabilities.py`、`agent/cli.py`、`agent/daemon.py`、`agent/hooks.py` 等 50 个文件，完整路径见 JSON。
- 19:00:51 · [439b479](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/439b4796505e6606108518c371fc9774748ae6f8) · Keep patch inspection JSON compatible with Windows console encodings
  变更文件：`README.md`、`agent/cli.py`、`app.py`、`tests/test_cli_encoding.py`。
- 21:14:27 · [1872557](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/1872557ebd10c9ed810d1db4819a5068b16f6d62) · Preserve failed acceptance test diagnostics for installed runtimes
  变更文件：`agent/inspection.py`。
- 21:21:35 · [b2952d1](https://github.com/yangzaipucci/codedesk-desktop-agent/commit/b2952d1a378238f9afa4d06929a446a0575b4fe2) · Handle transient Windows checkpoint locks and retain partial inspection results
  变更文件：`README.md`、`agent/capabilities.py`、`agent/cli.py`、`agent/daemon.py`、`agent/inspection.py`、`reports/custom_report.json`、`reports/mcp_report.json`、`tests/test_checkpoint_io.py`。
