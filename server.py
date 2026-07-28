"""Brainiall TTS MCP Server -- Hosted text-to-speech tools.

Exposes neural text-to-speech (54 voices, 9 languages, including native
Brazilian Portuguese) as MCP tools so AI agents can discover and use them
via the Model Context Protocol.

Deployed as a standalone FastMCP server with Streamable HTTP transport.
"""

import base64
import contextvars
import json
import os
import re
from typing import Annotated

import httpx
from fastmcp import FastMCP
from fastmcp.utilities.types import Audio
from pydantic import Field
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware

# Regex to strip internal hostnames / IPs from error messages
_INTERNAL_URL_RE = re.compile(
    r"https?://(?:apim-ai-apis\.azure-api\.net|20\.102\.72\.10|"
    r"10\.0\.0\.\d{1,3}|localhost:\d+|127\.0\.0\.1:\d+)[^\s\"']*"
)


def _sanitize_error(msg: str) -> str:
    """Remove internal URLs from error messages."""
    return _INTERNAL_URL_RE.sub("[backend]", str(msg))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TTS_API_URL = os.environ.get(
    "TTS_API_URL",
    "https://api.brainiall.com",
)
APIM_KEY = os.environ.get("APIM_KEY", "")
INTERNAL_API_KEY = os.environ.get("INTERNAL_API_KEY", "")

PRICE_PER_1K_CHARS_USD = 0.008

# Default voice per language when the caller doesn't pick one
DEFAULT_VOICE_BY_LANG = {
    "pt": "pf_dora",
    "pt-br": "pf_dora",
    "en": "af_heart",
    "en-us": "af_heart",
    "en-gb": "bf_emma",
    "es": "ef_dora",
    "fr": "ff_siwis",
    "fr-fr": "ff_siwis",
    "hi": "hf_alpha",
    "it": "if_sara",
    "ja": "jf_alpha",
    "zh": "zf_xiaoxiao",
    "cmn": "zf_xiaoxiao",
}

# Caller's API key propagated from HTTP request via middleware
_caller_key: contextvars.ContextVar[str] = contextvars.ContextVar("caller_key", default="")


class AuthForwardMiddleware(BaseHTTPMiddleware):
    """Capture caller's API key, serve health/discovery endpoints."""

    async def dispatch(self, request, call_next):
        from starlette.responses import JSONResponse

        path = request.url.path.rstrip("/")

        if path.endswith("/ping") or path.endswith("/health"):
            return JSONResponse({"status": "ok"})

        if path.endswith("/.well-known/mcp/server-card.json"):
            return JSONResponse({
                "serverInfo": {"name": "brainiall-tts", "version": "1.0.0"},
                "authentication": {"required": True, "schemes": ["api-key"]},
                "authorizationUrl": "https://app.brainiall.com",
            })

        key = (
            request.headers.get("Ocp-Apim-Subscription-Key", "")
            or request.headers.get("api-key", "")
        )
        if not key:
            auth = request.headers.get("Authorization", "")
            if auth.lower().startswith("bearer "):
                key = auth[7:]
        if not key:
            # Smithery gateway passes config as query parameters
            key = (
                request.query_params.get("brainiallApiKey", "")
                or request.query_params.get("apiKey", "")
                or request.query_params.get("api_key", "")
            )
        _caller_key.set(key)
        return await call_next(request)


mcp = FastMCP(
    "brainiall-tts",
    instructions=(
        "Hosted text-to-speech API with 54 neural voices across 9 languages "
        "(American/British English, Brazilian Portuguese, Spanish, French, "
        "Italian, Hindi, Japanese, Mandarin Chinese):\n"
        "1. **Speech Synthesis** -- synthesize_speech converts text to natural "
        "speech and returns playable WAV audio (24 kHz mono).\n"
        "2. **Voice Catalog** -- list_voices returns every available voice with "
        "language, gender, accent and quality grade.\n"
        "3. **Service Health** -- check_tts_service reports backend status.\n"
        "\nAuthentication: pass your Brainiall API key as a Bearer token "
        "(sign up at https://app.brainiall.com -- $10 free credits). "
        f"Usage is metered at ${PRICE_PER_1K_CHARS_USD}/1K characters."
    ),
)


def _add_auth_headers(headers: dict) -> dict:
    """Add authentication headers (caller key or APIM service key + internal key)."""
    key = _caller_key.get("") or APIM_KEY
    if key:
        headers["Authorization"] = f"Bearer {key}"
        headers["Ocp-Apim-Subscription-Key"] = key
    if INTERNAL_API_KEY:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    return headers


def _resolve_voice(language: str, voice: str | None) -> str:
    """Pick an explicit voice, or the default voice for the requested language."""
    if voice:
        return voice
    return DEFAULT_VOICE_BY_LANG.get((language or "pt").lower(), "pf_dora")


# ---------------------------------------------------------------------------
# Speech Synthesis
# ---------------------------------------------------------------------------

@mcp.tool(annotations={
    "title": "Synthesize Speech",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def synthesize_speech(
    text: Annotated[str, Field(description="Text to convert to speech (1-5000 characters per request)", min_length=1, max_length=5_000)],
    language: Annotated[str, Field(description="Language code: 'pt' (Brazilian Portuguese, default), 'en', 'en-gb', 'es', 'fr', 'it', 'hi', 'ja', 'zh'. Used to pick a default voice when 'voice' is omitted.")] = "pt",
    voice: Annotated[str | None, Field(description="Voice ID (e.g. 'pf_dora', 'pm_alex', 'af_heart', 'bm_george'). Overrides 'language'. Use list_voices for the full catalog.", default=None)] = None,
    speed: Annotated[float, Field(description="Speech speed multiplier (0.5 = half speed, 2.0 = double speed)", ge=0.5, le=2.0)] = 1.0,
    output_format: Annotated[str, Field(description="'audio' (default) returns playable MCP audio content; 'base64_json' returns JSON with the base64-encoded WAV plus metadata")] = "audio",
):
    """Convert text to natural-sounding speech.

    Returns WAV audio (16-bit PCM, 24 kHz mono) synthesized with neural voices.
    54 voices across 9 languages -- including 3 native Brazilian Portuguese
    voices (pf_dora, pm_alex, pm_santa). Usage is metered per character.

    Args:
        text: Text to convert to speech (max 5000 characters per request).
        language: Language code; selects the default voice when no voice is given.
        voice: Explicit voice ID (see list_voices). Overrides language.
        speed: Speech speed multiplier, 0.5-2.0.
        output_format: 'audio' for playable MCP audio content, 'base64_json'
            for a JSON object with the base64-encoded WAV and metadata.

    Returns:
        MCP audio content (audio/wav), or when output_format='base64_json' a
        dict with keys:
            - audio_base64 (str): Base64-encoded WAV bytes
            - mime_type (str): 'audio/wav'
            - voice (str): Voice used
            - characters (int): Characters billed
            - estimated_cost_usd (float): Estimated cost of this request
    """
    resolved_voice = _resolve_voice(language, voice)
    headers = {"Content-Type": "application/json"}
    _add_auth_headers(headers)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{TTS_API_URL}/v1/tts/synthesize",
                json={"text": text, "voice": resolved_voice, "speed": speed},
                headers=headers,
            )
            response.raise_for_status()
            audio_bytes = response.content
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        if exc.response.status_code in (401, 403):
            return {"error": "Authentication failed. Pass a valid Brainiall API key (get one at https://app.brainiall.com -- $10 free credits)."}
        if exc.response.status_code == 402:
            return {"error": "Insufficient credits. Top up at https://app.brainiall.com."}
        return {"error": f"Speech synthesis failed (HTTP {exc.response.status_code}). {_sanitize_error(detail)}".strip()}
    except Exception as exc:
        return {"error": f"TTS service temporarily unavailable: {_sanitize_error(str(exc))}"}

    if not audio_bytes[:4] == b"RIFF":
        return {"error": "TTS backend returned an unexpected (non-WAV) response."}

    if output_format == "base64_json":
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "mime_type": "audio/wav",
            "voice": resolved_voice,
            "characters": len(text),
            "estimated_cost_usd": round(len(text) / 1000 * PRICE_PER_1K_CHARS_USD, 6),
        }

    return Audio(data=audio_bytes, format="wav")


# ---------------------------------------------------------------------------
# Voice Catalog
# ---------------------------------------------------------------------------

@mcp.tool(annotations={
    "title": "List Voices",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def list_voices(
    language: Annotated[str | None, Field(description="Filter by language code (e.g. 'pt-br', 'en-us', 'ja'); omit for all 54 voices", default=None)] = None,
):
    """List available TTS voices with metadata.

    54 neural voices across 9 languages. Each voice has an ID (used in
    synthesize_speech), display name, gender, accent and quality grade.

    Args:
        language: Optional language filter (e.g. 'pt-br', 'en-us').

    Returns:
        dict with keys:
            - voices (list): Each with id, name, gender, accent, lang, grade
            - count (int): Number of voices returned
    """
    headers = {}
    _add_auth_headers(headers)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{TTS_API_URL}/v1/tts/voices",
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"Voice listing failed (HTTP {exc.response.status_code})"}
    except Exception as exc:
        return {"error": f"TTS service temporarily unavailable: {_sanitize_error(str(exc))}"}

    voices = data.get("voices", [])
    if language:
        lang = language.lower()
        voices = [v for v in voices if v.get("lang", "").lower().startswith(lang.split("-")[0])]
    return {"voices": voices, "count": len(voices)}


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------

@mcp.tool(annotations={
    "title": "Check TTS Service",
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
})
async def check_tts_service():
    """Check health status of the TTS API service.

    Returns:
        dict with keys:
            - status (str): 'healthy' or error state
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # The public TTS health route is owned by this MCP service. The
            # REST synthesis namespace intentionally does not expose a
            # /v1/tts/health endpoint.
            response = await client.get(f"{TTS_API_URL}/mcp/tts/health")
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        return {"error": f"Health check failed (HTTP {exc.response.status_code})"}
    except Exception as exc:
        return {"error": f"TTS service temporarily unavailable: {_sanitize_error(str(exc))}"}


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("tts://voices")
def tts_voices_reference() -> str:
    """Quick reference of voice IDs grouped by language."""
    return json.dumps({
        "pt-br": ["pf_dora (female)", "pm_alex (male)", "pm_santa (male)"],
        "en-us": ["af_heart", "af_bella", "af_nova", "af_sky", "am_adam", "am_michael", "am_onyx", "and 12 more"],
        "en-gb": ["bf_alice", "bf_emma", "bf_isabella", "bf_lily", "bm_daniel", "bm_fable", "bm_george", "bm_lewis"],
        "es": ["ef_dora", "em_alex", "em_santa"],
        "fr-fr": ["ff_siwis", "fm_gilles"],
        "hi": ["hf_alpha", "hf_beta", "hm_omega", "hm_psi"],
        "it": ["if_sara", "im_nicola"],
        "ja": ["jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"],
        "cmn": ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"],
        "note": "Call the list_voices tool for full metadata (gender, accent, grade).",
    })


@mcp.resource("tts://pricing")
def tts_pricing() -> str:
    """Pricing information for TTS API calls."""
    return json.dumps({
        "synthesize": f"${PRICE_PER_1K_CHARS_USD} per 1,000 characters",
        "list_voices": "free",
        "audio_format": "WAV, 16-bit PCM, 24 kHz mono",
        "max_characters_per_request": 5000,
        "signup": "https://app.brainiall.com -- $10 free credits on signup",
    })


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

@mcp.prompt()
def narrate_text(text: str, language: str = "pt") -> str:
    """Narrate a piece of text with the best-fitting voice.

    Args:
        text: The text to narrate.
        language: The language of the text (default 'pt').
    """
    return f"""\
Narrate the following text as natural speech:

Text: "{text}"

Steps:
1. Use list_voices with language="{language}" to see the available voices
2. Pick the most suitable voice for the content (gender/accent/grade)
3. Use synthesize_speech with the chosen voice; split the text into chunks
   of at most 5000 characters if it is longer
4. Return the audio and mention which voice was used"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", os.environ.get("FUNCTIONS_CUSTOMHANDLER_PORT", 8080)))
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        middleware=[Middleware(AuthForwardMiddleware)],
    )
