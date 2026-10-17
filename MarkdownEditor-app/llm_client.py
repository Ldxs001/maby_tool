# -*- coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
"""LLM 统一客户端 — LM Studio / Ollama（OpenAI 兼容 HTTP API），纯标准库零依赖。

移植自 structured-writer（Qwen 写作智能体）samedi 架构的成熟实现：
  - LM Studio:  http://<host>:1234/v1/chat/completions
  - Ollama:     http://<host>:11434/api/chat
模型列表、配置校验、调用超时与错误归一互相独立，供 md_server.py 注解/润色/测试共用。
"""
import json
import time
import urllib.request
import urllib.error


class LLMError(Exception):
    pass


class LLMClient:
    """LLM 统一客户端。config 形如:
    {"backend": "lmstudio"|"ollama", "base_url": "...", "model": "",
     "timeout": 180, "max_tokens": 2048, "temperature": 0.7}
    """

    def __init__(self, config=None):
        cfg = config or {}
        self.backend = (cfg.get("backend") or "lmstudio").lower()
        self.base_url = (cfg.get("base_url") or "").rstrip("/")
        self.model = cfg.get("model") or ""
        try:
            self.timeout = int(cfg.get("timeout", 180))
        except Exception:
            self.timeout = 180
        try:
            self.max_tokens = int(cfg.get("max_tokens", 2048))
        except Exception:
            self.max_tokens = 2048
        try:
            self.temperature = float(cfg.get("temperature", 0.7))
        except Exception:
            self.temperature = 0.7
        if not self.base_url:
            self.base_url = ("http://localhost:1234" if self.backend == "lmstudio"
                             else "http://localhost:11434")

    # ---- 端点与载荷 ----
    def _chat_url(self):
        if self.backend == "ollama":
            return self.base_url + "/api/chat"
        return self.base_url + "/v1/chat/completions"

    def _models_url(self):
        if self.backend == "ollama":
            return self.base_url + "/api/tags"
        return self.base_url + "/v1/models"

    def list_models(self):
        """取当前后端可用模型名列表。LM Studio: data[].id；Ollama: models[].name。"""
        req = urllib.request.Request(self._models_url(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=min(self.timeout, 15)) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as e:
            raise LLMError(str(e))
        if self.backend == "ollama":
            names = [m.get("name", "") for m in data.get("models", [])]
        else:
            names = [m.get("id", "") for m in data.get("data", [])]
        return [n for n in names if n]

    def test_connection(self):
        """返回 (ok, message)。模型列表可为空但连接通 —— 也算成功（提示可刷新）。"""
        try:
            models = self.list_models()
            if models:
                return True, "连接成功，可用模型 %d 个：%s" % (
                    len(models), "、".join(models[:6]) + ("…" if len(models) > 6 else ""))
            return True, "连接成功，但后端未返回模型列表。"
        except Exception as e:
            return False, "连接失败：%s" % e

    def chat(self, messages, max_tokens=None, temperature=None):
        """一次对话，返回回复文本。messages 为 [{"role","content"}, ...]。"""
        mt = max_tokens or self.max_tokens
        if self.backend == "ollama":
            payload = json.dumps({
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_predict": mt,
                            "temperature": temperature if temperature is not None else self.temperature},
            }).encode("utf-8")
        else:
            p = {"messages": messages, "max_tokens": mt,
                 "temperature": temperature if temperature is not None else self.temperature}
            if self.model:
                p["model"] = self.model
            payload = json.dumps(p).encode("utf-8")
        req = urllib.request.Request(self._chat_url(), data=payload,
                                     headers={"Content-Type": "application/json"},
                                     method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            raise LLMError("HTTP %d: %s" % (e.code, err[:300]))
        except urllib.error.URLError as e:
            raise LLMError("连接失败: %s" % getattr(e, "reason", e))
        except Exception as e:
            raise LLMError("LLM 调用异常: %s" % e)
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
            if self.backend == "ollama":
                return data.get("message", {}).get("content", "").strip()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise LLMError("响应解析失败: %s" % e)

    # ---- 本工具业务封装：润色 / 注解 ----
    def polish(self, text):
        """对话式润色（保持语义与长度，优化表达）。保留 markdown 标记不动。"""
        import html as _h
        sysp = ("你是一个中文写作润色助手。用户给你一段文本，请润色优化："
                "保持原意、结构、篇幅和 Markdown 标记（#、*、`、链接等）完全不变，"
                "仅优化表达的通顺、准确与书面化。只输出润色后的文本，不要解释。")
        return self.chat([{"role": "system", "content": sysp},
                          {"role": "user", "content": text}])

    def explain(self, text):
        """注解式解释：对选中片段给出简要的注释/解释，供用户作为备注模板确认后使用。"""
        sysp = ("你是一个 Markdown 文档注释助手。用户给出一段文本，请你为它写一条"
                "简洁的备注/批注：解释它的含义或补充要点，2-4 句，第一人称可省略。"
                "直接输出备注内容，不要引号、不要'备注：'前缀。")
        return self.chat([{"role": "system", "content": sysp},
                          {"role": "user", "content": text}])