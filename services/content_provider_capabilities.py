"""Declared Content Studio provider capabilities.

This is deliberately provider-neutral: the UI and route validation both use the
same small contract, so an unavailable output type cannot be submitted as if it
were supported.
"""

from __future__ import annotations

from typing import Any


PROVIDER_CAPABILITIES: dict[str, dict[str, Any]] = {
    "mock": {
        "label": "Mock Provider",
        "supported_output_types": ("image",),
        "development_only": True,
    },
}


def provider_capabilities(provider: str) -> dict[str, Any] | None:
    capability = PROVIDER_CAPABILITIES.get(str(provider or "").strip())
    return dict(capability) if capability else None


def supports_output_type(provider: str, output_type: str) -> bool:
    capability = provider_capabilities(provider)
    return bool(
        capability
        and output_type in capability["supported_output_types"]
    )


def public_provider_capabilities() -> dict[str, dict[str, Any]]:
    return {
        provider: {
            **capability,
            "supported_output_types": list(capability["supported_output_types"]),
        }
        for provider, capability in PROVIDER_CAPABILITIES.items()
    }
