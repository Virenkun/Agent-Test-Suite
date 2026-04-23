from dataclasses import dataclass
from typing import Any

from retell import Retell

from app.config import get_settings
from app.core.exceptions import ExternalServiceError
from app.core.logging import get_logger
from app.models.persona import Persona
from app.models.test_case import TestCase

log = get_logger(__name__)


@dataclass
class PlacedCall:
    retell_call_id: str
    raw: dict[str, Any]


def build_dynamic_variables(persona: Persona, test_case: TestCase) -> dict[str, str]:
    constraints = persona.constraints or {}
    constraints_text = "\n".join(f"- {k}: {v}" for k, v in constraints.items()) or "None"
    return {
        "persona_name": persona.name,
        "persona_tone": persona.tone or "neutral",
        "persona_personality": persona.personality or "",
        "persona_goal": persona.goal or "",
        "persona_constraints": constraints_text,
        "persona_instructions": persona.prompt_instructions or "",
        "test_case_context": test_case.context or "",
    }


class RetellClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.retell_api_key:
            raise ExternalServiceError("RETELL_API_KEY not configured")
        self._client = Retell(api_key=settings.retell_api_key)
        self._agent_id = settings.retell_agent_id
        self._from_number = settings.retell_from_number

    def place_call(
        self,
        *,
        to_number: str,
        dynamic_variables: dict[str, str],
        metadata: dict[str, Any] | None = None,
        max_duration_sec: int | None = None,
    ) -> PlacedCall:
        if not self._agent_id or not self._from_number:
            raise ExternalServiceError("RETELL_AGENT_ID and RETELL_FROM_NUMBER must be set")
        # Retell's create_phone_call does not accept a per-call duration cap.
        # Duration is enforced agent-side (Agent → End Call → Max Call Duration).
        # We forward max_duration_sec in metadata so it's visible in the Retell dashboard
        # and available if Retell adds per-call support later.
        call_metadata = {**(metadata or {})}
        if max_duration_sec:
            call_metadata["max_duration_sec"] = str(max_duration_sec)
        try:
            call = self._client.call.create_phone_call(
                from_number=self._from_number,
                to_number=to_number,
                override_agent_id=self._agent_id,
                retell_llm_dynamic_variables=dynamic_variables,
                metadata=call_metadata,
            )
        except Exception as e:
            log.error("retell_place_call_failed", error=str(e))
            raise ExternalServiceError(f"Retell API error: {e}") from e

        raw = call.model_dump() if hasattr(call, "model_dump") else dict(call)
        call_id = raw.get("call_id") or raw.get("id")
        if not call_id:
            raise ExternalServiceError("Retell response missing call_id")
        return PlacedCall(retell_call_id=str(call_id), raw=raw)

    def verify_webhook_signature(self, *, payload: bytes, signature: str) -> bool:
        """Verify a Retell webhook signature.

        Retell sends `x-retell-signature: v=<timestamp>,d=<hex>` where
        hex = HMAC-SHA256(api_key, f"v{timestamp}.{raw_body}").

        If RETELL_WEBHOOK_SECRET is blank we accept everything (dev mode /
        dashboard "Test Webhook" button, which sends synthetic unsigned events).
        """
        settings = get_settings()
        if not settings.retell_webhook_secret:
            return True

        # Try the official SDK helper first
        try:
            from retell import Retell as _Retell  # type: ignore

            verified = _Retell.verify(
                payload, api_key=settings.retell_api_key, signature=signature
            )
            if verified:
                return True
        except Exception:
            pass

        # Manual fallback matching Retell's scheme
        import hashlib
        import hmac

        parts = dict(
            part.split("=", 1) for part in signature.split(",") if "=" in part
        )
        ts = parts.get("v")
        sig = parts.get("d")
        if not ts or not sig:
            return False

        secret = (settings.retell_api_key or settings.retell_webhook_secret).encode()
        signed = f"v{ts}.".encode() + payload
        expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, sig)
