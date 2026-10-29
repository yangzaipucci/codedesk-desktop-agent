"""Non-secret preferences on disk; API keys only in memory or Windows Vault."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

PRESETS = {
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com", "model": "deepseek-flash"},
    "openai": {"label": "OpenAI", "base_url": "https://api.openai.com/v1", "model": ""},
    "qwen": {"label": "通义千问 / 百炼", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
    "moonshot": {"label": "Kimi / Moonshot", "base_url": "https://api.moonshot.cn/v1", "model": "kimi-k2.5"},
    "glm": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4.7"},
    "custom": {"label": "自定义兼容接口", "base_url": "", "model": ""},
}


def data_directory() -> Path:
    override = os.environ.get("CODEDESK_DATA_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CodeDesk"
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_endpoint(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlparse(value)
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("请填写服务地址，不要在地址中填写 Key、用户名或查询参数。")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}):
        raise ValueError("远程模型接口必须使用 HTTPS；本机接口可以使用 HTTP。")
    if value.endswith("/chat/completions"):
        value = value[:-len("/chat/completions")]
    return value


class Settings:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "settings.json"
        self.value = {"provider": "deepseek", **PRESETS["deepseek"], "workspace": "", "max_steps": 20, "budget_tokens": 100000, "run_timeout": 300, "mcp_servers": {}}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                self.value.update({k: v for k, v in saved.items() if k in self.value})
            except (ValueError, OSError):
                pass
        self.memory_keys: dict[str, str] = {}

    @staticmethod
    def _vault():
        if os.name != "nt":
            raise ValueError("此版本只支持 Windows 凭据管理器，请使用仅本次运行。")
        from keyring.backends.Windows import WinVaultKeyring
        return WinVaultKeyring()

    def _account(self, endpoint: str | None = None) -> str:
        return hashlib.sha256((endpoint or self.value["base_url"]).encode()).hexdigest()

    def key(self, endpoint: str | None = None) -> str:
        account = self._account(endpoint)
        if account in self.memory_keys:
            return self.memory_keys[account]
        try:
            return self._vault().get_password("CodeDesk", account) or ""
        except Exception:
            return ""

    def public(self) -> dict:
        return {**self.value, "has_key": bool(self.key()), "presets": PRESETS}

    def _remove_remembered(self, account: str, strict: bool = False):
        try:
            vault = self._vault()
            remembered = vault.get_password("CodeDesk", account)
        except Exception as error:
            if strict:
                raise ValueError("系统凭据管理器不可用，无法确认已删除保存的 Key。请在 Windows 凭据管理器中检查。") from error
            return
        if remembered:
            try:
                vault.delete_password("CodeDesk", account)
                if vault.get_password("CodeDesk", account):
                    raise ValueError("credential still present")
            except Exception as error:
                raise ValueError("系统中保存的 Key 未能删除，请重试或在 Windows 凭据管理器中删除 CodeDesk 凭据。") from error

    def save(self, payload: dict) -> dict:
        value = dict(self.value)
        for name in ("provider", "model", "workspace", "max_steps", "budget_tokens", "run_timeout", "mcp_servers"):
            if name in payload:
                value[name] = payload[name]
        value["base_url"] = validate_endpoint(str(payload.get("base_url", value["base_url"])))
        if not isinstance(value["model"], str):
            raise ValueError("模型名称应为文本。")
        value["model"] = value["model"].strip()
        value["max_steps"] = max(1, min(60, int(value["max_steps"])))
        value["budget_tokens"] = max(1000, min(1000000, int(value["budget_tokens"])))
        value["run_timeout"] = max(10, min(1800, int(value["run_timeout"])))
        if not isinstance(value["mcp_servers"], dict):
            raise ValueError("MCP 配置应为 JSON 对象。")
        if value["workspace"]:
            workspace = Path(value["workspace"]).expanduser().resolve()
            if not workspace.is_dir():
                raise ValueError("工作目录不存在，请重新选择。")
            value["workspace"] = str(workspace)
        key = str(payload.get("api_key", "")).strip()
        account = self._account(value["base_url"])
        if payload.get("forget_key"):
            self._remove_remembered(account, strict=True)
            self.memory_keys.pop(account, None)
        elif key:
            if payload.get("remember_key"):
                try:
                    self._vault().set_password("CodeDesk", account, key)
                except Exception as error:
                    raise ValueError("系统凭据存储不可用。取消勾选保存 Key 后可仅在本次运行使用。") from error
            else:
                # Replace any previous remembered key with a session-only value.
                self._remove_remembered(account)
            self.memory_keys[account] = key
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
        self.value = value
        return self.public()

    def redact(self, text: str) -> str:
        for secret in set(self.memory_keys.values()) | {self.key()}:
            if secret:
                text = text.replace(secret, "[API KEY 已隐藏]")
        return text
