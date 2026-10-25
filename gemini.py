"""Gemini REST adapter. No automatic retries, model changes, or provider fallback."""

import json
import re
from urllib import error, request


class ProviderError(RuntimeError):
    def __init__(self, message, code="provider_error", **details):
        super().__init__(message)
        self.details = {"code": code, **details}


class Gemini:
    name = "gemini"

    def __init__(self, api_key, model="gemini-3.5-flash-lite", timeout=45, max_output_tokens=2048):
        if not api_key or not api_key.strip():
            raise ValueError("Set GOOGLE_API_KEY (or GEMINI_API_KEY) to a non-empty value before starting a live run")
        if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
            raise ValueError("Model must be a model ID, without a URL or models/ prefix")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens

    def generate(self, contents, declarations, instruction):
        payload = {
            "systemInstruction": {"parts": [{"text": instruction}]},
            "contents": contents,
            "tools": [{"functionDeclarations": declarations}],
            "toolConfig": {"functionCallingConfig": {"mode": "ANY"}},
            "generationConfig": {"maxOutputTokens": self.max_output_tokens},
        }
        req = request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = json.load(response)
        except error.HTTPError as exc:
            message = exc.read(4096).decode("utf-8", errors="backslashreplace").replace(self.api_key, "[REDACTED]")
            retry_after = exc.headers.get("Retry-After")
            raise ProviderError(f"Gemini HTTP {exc.code}: {message}. Retry-After: {retry_after}. No automatic retry was made.",
                                code="provider_rate_limit" if exc.code == 429 else "provider_http_error",
                                http_status=exc.code, retry_after=retry_after,
                                recovery="Review the provider error and reported cooldown, then explicitly resume the run. No retry or provider switch was made.") from exc
        except (error.URLError, TimeoutError, OSError, ValueError) as exc:
            timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError)
            raise ProviderError(f"Gemini request failed: {str(exc).replace(self.api_key, '[REDACTED]')}",
                                code="provider_timeout" if timed_out else "provider_request_error",
                                recovery="Check connectivity/provider availability, then explicitly resume. No returned tool call was executed.") from exc
        if not isinstance(data, dict):
            raise ProviderError("Gemini returned a non-object JSON response", code="provider_invalid_response")
        candidates = data.get("candidates", [])
        if not candidates:
            raise ProviderError(f"Gemini returned no candidate: {data.get('promptFeedback', {})}")
        candidate = candidates[0]
        # Never execute partial tool calls after a token limit or blocked response.
        if candidate.get("finishReason") != "STOP":
            raise ProviderError(f"Gemini response incomplete: {candidate.get('finishReason', 'missing finishReason')}")
        content = candidate.get("content")
        if not isinstance(content, dict) or content.get("role") != "model" or not content.get("parts"):
            raise ProviderError("Gemini returned invalid model content")
        # Preserve the full content, including opaque thought signatures, for the next request.
        usage = data.get("usageMetadata", {})
        if not isinstance(usage, dict):
            raise ProviderError("Gemini returned invalid token usage", code="provider_invalid_response")
        return content, usage
