from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

import httpx


CLASSIFICATION_ORDER = {
    "public": 0,
    "open": 0,
    "internal": 1,
    "protected-a": 2,
    "protected-b": 3,
    "protected-c": 4,
    "secret": 5,
    "top-secret": 6,
}


@dataclass
class AIProvider:
    provider_id: str
    name: str
    base_url: str
    model: str
    api_key_env: Optional[str] = None
    enabled: bool = True
    sovereign: bool = False
    jurisdiction: Optional[str] = None
    max_classification: str = "public"
    request_timeout_seconds: float = 60.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def api_key(self) -> Optional[str]:
        return os.getenv(self.api_key_env) if self.api_key_env else None


@dataclass
class AIEvidenceContract:
    summary: str
    claims: List[Dict[str, Any]] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)
    information_gaps: List[str] = field(default_factory=list)
    recommended_actions: List[Dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.5
    model_provider: Optional[str] = None
    model_name: Optional[str] = None
    policy: Dict[str, Any] = field(default_factory=lambda: {
        "advisory_only": True,
        "deterministic_core_is_source_of_truth": True,
        "human_authorization_required_for_consequential_actions": True,
    })

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["confidence"] = max(0.0, min(1.0, float(self.confidence)))
        return data


def _classification_value(value: str) -> int:
    return CLASSIFICATION_ORDER.get((value or "public").strip().lower(), 99)


def provider_allows(provider: AIProvider, data_classification: str) -> bool:
    return _classification_value(data_classification) <= _classification_value(provider.max_classification)


def configured_providers() -> Dict[str, AIProvider]:
    """Return configured providers without exposing secrets.

    The gateway intentionally uses an OpenAI-compatible HTTP contract so Canadian,
    sovereign, local and commercial providers can be added without changing agent code.
    """
    providers: Dict[str, AIProvider] = {}

    if os.getenv("OPENAI_API_KEY"):
        providers["openai"] = AIProvider(
            provider_id="openai",
            name="OpenAI",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            api_key_env="OPENAI_API_KEY",
            max_classification=os.getenv("OPENAI_MAX_CLASSIFICATION", "public"),
            jurisdiction=os.getenv("OPENAI_JURISDICTION"),
            metadata={"recommended_role": "balanced reasoning/cost"},
        )

    # Generic sovereign/Canadian provider. Configure when a suitable Canadian model
    # is selected; no code changes are needed if it exposes an OpenAI-compatible API.
    if os.getenv("CANADIAN_AI_BASE_URL") and os.getenv("CANADIAN_AI_MODEL"):
        providers["canadian-ai"] = AIProvider(
            provider_id="canadian-ai",
            name=os.getenv("CANADIAN_AI_NAME", "Canadian AI Provider"),
            base_url=os.environ["CANADIAN_AI_BASE_URL"].rstrip("/"),
            model=os.environ["CANADIAN_AI_MODEL"],
            api_key_env="CANADIAN_AI_API_KEY" if os.getenv("CANADIAN_AI_API_KEY") else None,
            sovereign=True,
            jurisdiction="CA",
            max_classification=os.getenv("CANADIAN_AI_MAX_CLASSIFICATION", "protected-b"),
        )

    if os.getenv("LOCAL_AI_BASE_URL") and os.getenv("LOCAL_AI_MODEL"):
        providers["local-ai"] = AIProvider(
            provider_id="local-ai",
            name=os.getenv("LOCAL_AI_NAME", "Local / On-Prem AI"),
            base_url=os.environ["LOCAL_AI_BASE_URL"].rstrip("/"),
            model=os.environ["LOCAL_AI_MODEL"],
            api_key_env="LOCAL_AI_API_KEY" if os.getenv("LOCAL_AI_API_KEY") else None,
            sovereign=True,
            jurisdiction=os.getenv("LOCAL_AI_JURISDICTION", "local"),
            max_classification=os.getenv("LOCAL_AI_MAX_CLASSIFICATION", "secret"),
        )

    return providers


def select_provider(
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
) -> AIProvider:
    providers = configured_providers()
    ordered: List[AIProvider] = []
    if preferred_provider:
        chosen = providers.get(preferred_provider)
        if not chosen:
            raise ValueError(f"AI provider is not configured: {preferred_provider}")
        ordered.append(chosen)
    ordered.extend(p for key, p in providers.items() if key != preferred_provider)

    for provider in ordered:
        if not provider.enabled:
            continue
        if require_sovereign and not provider.sovereign:
            continue
        if provider_allows(provider, data_classification):
            return provider
    raise ValueError(
        f"No configured AI provider satisfies classification={data_classification!r} "
        f"and require_sovereign={require_sovereign}"
    )


def _extract_json(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("AI provider returned non-JSON output") from exc


async def complete_json(
    *,
    system_prompt: str,
    user_payload: Dict[str, Any],
    data_classification: str = "public",
    preferred_provider: Optional[str] = None,
    require_sovereign: bool = False,
    temperature: float = 0.1,
) -> Dict[str, Any]:
    provider = select_provider(data_classification, preferred_provider, require_sovereign)
    headers = {"Content-Type": "application/json"}
    if provider.api_key:
        headers["Authorization"] = f"Bearer {provider.api_key}"

    body = {
        "model": provider.model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, default=str, separators=(",", ":"))},
        ],
    }
    async with httpx.AsyncClient(timeout=provider.request_timeout_seconds) as client:
        response = await client.post(f"{provider.base_url}/chat/completions", headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("AI provider returned no choices")
    content = ((choices[0].get("message") or {}).get("content")) or ""
    result = _extract_json(content)
    result.setdefault("model_provider", provider.provider_id)
    result.setdefault("model_name", provider.model)
    return result


def provider_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "provider_id": p.provider_id,
            "name": p.name,
            "model": p.model,
            "base_url": p.base_url,
            "sovereign": p.sovereign,
            "jurisdiction": p.jurisdiction,
            "max_classification": p.max_classification,
            "enabled": p.enabled,
            "metadata": p.metadata,
        }
        for p in configured_providers().values()
    ]
