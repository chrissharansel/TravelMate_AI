"""All GitHub Copilot SDK access lives here. Nothing in this file is ever sent to React.
Sessions deny every permission request and expose no built-in tools, so the model can only return text:
it cannot run code, touch files or browse. Tools are plain Python functions called by our orchestrator."""
import asyncio, json
from copilot import CopilotClient
from copilot.session import PermissionDecisionUserNotAvailable
from .config import get_settings

_client: CopilotClient | None = None
_lock = asyncio.Lock()


class CopilotUnavailable(Exception):
    """Raised with a user-safe message when Copilot cannot answer."""


def _deny_all(request, invocation):
    return PermissionDecisionUserNotAvailable()


async def start_copilot():
    global _client
    async with _lock:
        if _client is None:
            c = CopilotClient()   # bundled runtime; uses env token or the signed-in CLI user
            await c.start()
            _client = c
    return _client


async def stop_copilot():
    global _client
    if _client is not None:
        try:
            await _client.stop()
        finally:
            _client = None


def friendly(e: Exception) -> str:
    t = str(e).lower()
    if any(k in t for k in ("quota", "limit", "429", "rate")):
        return "Copilot usage limit reached for your plan. Wait for the limit to reset, then retry."
    if any(k in t for k in ("auth", "login", "token", "401", "unauthor")):
        return "Copilot is not authenticated. Set COPILOT_GITHUB_TOKEN or sign in with the Copilot CLI."
    if "model" in t:
        return "The selected model is not available on your plan. Set COPILOT_MODEL=auto."
    return f"Copilot error: {type(e).__name__}: {e}"


async def ask(prompt: str, model: str | None = None) -> str:
    s = get_settings()
    client = await start_copilot()
    try:
        async with await client.create_session(
            on_permission_request=_deny_all, model=model or s.copilot_model, available_tools=[],
        ) as session:
            event = await asyncio.wait_for(
                session.send_and_wait(prompt, timeout=s.copilot_timeout_seconds),
                timeout=s.copilot_timeout_seconds + 5)
    except Exception as e:
        raise CopilotUnavailable(friendly(e)) from e
    if event is None or not getattr(event.data, "content", None):
        raise CopilotUnavailable("Copilot returned no content.")
    return event.data.content


def extract_json(text: str) -> dict | None:
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch == "{":
            try:
                obj, _ = dec.raw_decode(text[i:])
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                continue
    return None


async def ask_json(instructions: str, payload: str) -> dict | None:
    """Ask for a JSON object. Retries once when the reply is not valid JSON. Returns None if still invalid."""
    prompt = f"{instructions}\n\nRespond with ONE JSON object only. No markdown, no commentary.\n\n{payload}"
    for _ in range(2):
        obj = extract_json(await ask(prompt))
        if obj is not None:
            return obj
    return None


async def auth_status() -> dict:
    st = await (await start_copilot()).get_auth_status()
    return st.to_dict() if hasattr(st, "to_dict") else {"raw": str(st)}


async def models() -> list[str]:
    return [getattr(m, "id", str(m)) for m in await (await start_copilot()).list_models()]
