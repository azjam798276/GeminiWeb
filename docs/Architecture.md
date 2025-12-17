
1. High-level architecture
Goal: Treat Gemini-via-web as just another provider behind your OpenAI-compatible API, but:
It pulls headers dynamically (UA, X-Client-Data, etc.) from a store populated by a real browser


It uses your own Pro account cookies


It detects which model you actually got (flash vs pro) and returns that to the router


Rough component diagram:
             ┌────────────────────────────┐
              │       Client (OpenAI)      │
              └─────────────┬──────────────┘
                            │
                            ▼
              ┌────────────────────────────┐
              │    ModelRouter / Gateway   │
              │  (gpt-4, gpt-4.1, etc.)    │
              └─────────────┬──────────────┘
    ┌───────────────────────┼────────────────────────────┐
    │                       │                            │
    ▼                       ▼                            ▼
┌────────────┐       ┌───────────────┐           ┌────────────────┐
│ GeminiWeb  │       │ DeepSeekProv  │           │ OtherProvider… │
│  Provider  │       └───────────────┘           └────────────────┘
└─────┬──────┘
      │ uses
      ▼
┌───────────────┐      ┌─────────────────┐
│ HeaderStore   │      │ CookieStore     │
│ (UA, X-CD…)   │      │ (Gemini cookies)│
└─────┬─────────┘      └───────┬────────┘
      │                        │
      ▼                        ▼
           ┌───────────────────────────────┐
           │       GeminiWebSession       │
           │  (SNlM0e, fetch, retry, etc.)│
           └───────────────────────────────┘


2. Core pieces in pseudo-code
All pseudo-code is Python-ish and provider-agnostic; you’ll drop in your actual HTTP client and endpoint later.
2.1. Config & stores
# intents: what the *user* or your logical model wants
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


class ModelTier(str, Enum):
    GEMINI_FLASH = "gemini-2.5-flash"
    GEMINI_PRO = "gemini-2.5-pro"
    GEMINI_ANY = "gemini-2.5-any"   # "best available"


@dataclass
class CompletionIntent:
    logical_model: str          # e.g. "gpt-4", "gpt-4.1"
    min_tier: ModelTier         # what you *want* at least
    messages: List[Dict[str, Any]]
    extra: Dict[str, Any] = None


@dataclass
class CompletionResult:
    provider_name: str
    actual_model: str           # e.g. "gemini-2.5-pro"
    tier: ModelTier             # normalized tier
    content: str
    raw_response: Any

Header store – populated once from a real browser (manual step / helper tool):
class HeaderStore:
    """
    Stores stable fingerprint headers captured from your real Chrome.
    You fill this using a separate helper script, not here.
    """

    def __init__(self, path: str):
        self.path = path
        self._cache: Optional[Dict[str, str]] = None

    def _load(self) -> Dict[str, str]:
        if self._cache is not None:
            return self._cache
        try:
            import json, os
            if not os.path.exists(self.path):
                raise FileNotFoundError(self.path)
            with open(self.path, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except Exception:
            self._cache = {}
        return self._cache or {}

    def get_headers(self) -> Dict[str, str]:
        data = self._load()
        # Minimal set. You can store more (Sec-CH-UA, etc.) if you want.
        return {
            "User-Agent": data.get("user_agent", ""),
            "X-Client-Data": data.get("x_client_data", ""),
            # You can add others here if you captured them:
            # "Sec-Ch-Ua": data.get("sec_ch_ua", ""),
        }

Cookie store – use your own Pro session cookies:
class CookieStore:
    """
    Holds cookies for gemini.google.com from your browser.
    Keep this file private; it's your auth.
    """

    def __init__(self, path: str):
        self.path = path
        self._cookies = None

    def _load(self):
        if self._cookies is not None:
            return self._cookies
        import json, os
        if not os.path.exists(self.path):
            raise FileNotFoundError(self.path)
        with open(self.path, "r", encoding="utf-8") as f:
            self._cookies = json.load(f)
        return self._cookies

    def as_dict(self) -> Dict[str, str]:
        return self._load()

2.2. GeminiWebSession (edge-facing HTTP helper)
This encapsulates SNlM0e, dynamic header injection, retries, etc.
class GeminiWebSession:
    def __init__(self, header_store: HeaderStore, cookie_store: CookieStore):
        self.header_store = header_store
        self.cookie_store = cookie_store
        self._snlm0e: Optional[str] = None

    def _refresh_snlm0e(self):
        """
        Fetches SNlM0e token from gemini.google.com.
        You already have logic for this in g4f; just wrap it here.
        """
        headers = self.header_store.get_headers()
        cookies = self.cookie_store.as_dict()

        # PSEUDO HTTP – replace with curl_cffi/requests/etc.
        resp = http_get("https://gemini.google.com/app", headers=headers, cookies=cookies)

        token = extract_snlm0e_from_html(resp.text)  # your existing parser
        if not token:
            raise RuntimeError("Failed to extract SNlM0e")
        self._snlm0e = token

    def ensure_snlm0e(self):
        if not self._snlm0e:
            self._refresh_snlm0e()

    def build_headers(self, extra: Dict[str, str] = None) -> Dict[str, str]:
        """
        Merge base fingerprint headers with any call-specific headers.
        """
        base = self.header_store.get_headers().copy()
        base.update({
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://gemini.google.com",
            "Referer": "https://gemini.google.com/app",
            # DO NOT put model hashes here; let backend choose from your entitlements.
        })
        if extra:
            base.update(extra)
        return base

    def build_cookies(self) -> Dict[str, str]:
        cookies = self.cookie_store.as_dict().copy()
        # SNlM0e sometimes goes in cookies / body depending on your implementation.
        if self._snlm0e:
            cookies["SNlM0e"] = self._snlm0e
        return cookies

    def call_chat_endpoint(self, payload: Dict[str, Any]) -> Any:
        """
        Make the actual POST to Gemini's consumer chat backend.
        No hardcoded model forcing here; payload mirrors browser.
        """
        self.ensure_snlm0e()

        headers = self.build_headers()
        cookies = self.build_cookies()

        # PSEUDO
        resp = http_post(
            "https://gemini.google.com/_/SomeConsumerChatEndpoint",
            headers=headers,
            cookies=cookies,
            json=payload,
            timeout=60,
        )

        if resp.status_code == 401:
            # Cookie expired; retry once after refresh.
            self._snlm0e = None
            self._refresh_snlm0e()
            cookies = self.build_cookies()
            resp = http_post(
                "https://gemini.google.com/_/SomeConsumerChatEndpoint",
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=60,
            )

        resp.raise_for_status()
        return resp.json()  # or streaming handler

2.3. GeminiWebProvider class
This is what your router will use; it wraps the session and does:
Message → browser-like payload


Response → text + actual_model detection


class GeminiWebProvider:
    name = "GeminiWeb"

    def __init__(self, session: GeminiWebSession):
        self.session = session

    # Optional: what this provider *claims* it can do
    def supports_intent(self, intent: CompletionIntent) -> bool:
        # Example policy: GeminiWeb used for any GPT-4-ish tier
        return intent.logical_model in {"gpt-4", "gpt-4.1", "gpt-4.1-mini"}

    def _intent_to_payload(self, intent: CompletionIntent) -> Dict[str, Any]:
        """
        Convert OpenAI-style messages into whatever Gemini's web backend expects.
        This is where you mirror the real network payload from your browser.
        """
        # This is deliberately abstract; you fill it with what your HAR shows.
        messages = intent.messages

        # Example placeholder:
        return {
            "conversation": messages,
            # ... plus other fields you know Gemini's consumer endpoint needs,
            # mirroring your browser traffic.
        }

    def _detect_tier_from_response(self, resp_json: Any) -> (str, ModelTier):
        """
        Inspect the response to guess the model name and normalize to a tier.
        This is a stub – you implement the actual heuristics based on real traffic.
        """
        # Pseudo fields; you must inspect your own responses:
        # maybe resp_json has something like resp_json["model"], or buried metadata.

        model_name = None

        # Example heuristic stub:
        if isinstance(resp_json, dict) and "model" in resp_json:
            model_name = resp_json["model"]
        else:
            # TODO: parse streaming chunks / metadata, etc.
            model_name = "gemini-2.5-flash"  # safe default if unknown

        # Normalize to tier
        if "pro" in model_name:
            tier = ModelTier.GEMINI_PRO
        elif "flash" in model_name:
            tier = ModelTier.GEMINI_FLASH
        else:
            tier = ModelTier.GEMINI_FLASH  # default conservative

        return model_name, tier

    def complete(self, intent: CompletionIntent) -> CompletionResult:
        payload = self._intent_to_payload(intent)
        resp_json = self.session.call_chat_endpoint(payload)

        # Extract text content
        content = extract_text_from_response(resp_json)  # your parser

        actual_model, tier = self._detect_tier_from_response(resp_json)

        return CompletionResult(
            provider_name=self.name,
            actual_model=actual_model,
            tier=tier,
            content=content,
            raw_response=resp_json,
        )

Key point: _detect_tier_from_response is where you leverage your Gemini Pro account.
 If the backend routes you to Pro, that model name will show up here. You’re not forcing it; you’re just detecting and surfacing it to your router.

3. Integration into your rotation / router
Assume you already have multiple providers and a router that chooses between them. We add:
A simple tier check: if provider returns a tier < intent.min_tier, we mark it as “insufficient” and optionally try the next provider.


3.1. Router skeleton
class ModelRouter:
    def __init__(self, providers: List[Any]):
        self.providers = providers  # e.g. [GeminiWebProvider(...), DeepSeekProvider(...), ...]

    def route(self, intent: CompletionIntent) -> CompletionResult:
        errors = []

        for provider in self.providers:
            if hasattr(provider, "supports_intent") and not provider.supports_intent(intent):
                continue

            try:
                result = provider.complete(intent)

                # Check tier
                if intent.min_tier is ModelTier.GEMINI_PRO:
                    # require at least PRO-ish quality
                    if result.tier != ModelTier.GEMINI_PRO:
                        # log "model drift" and optionally try next provider
                        errors.append(
                            f"{provider.name} returned {result.actual_model} ({result.tier}), "
                            f"below required {intent.min_tier}"
                        )
                        continue  # try next provider
                # If we reach here, we accept the result
                self._log_routing(intent, result)
                return result

            except Exception as e:
                errors.append(f"{provider.name} failed: {e!r}")
                continue

        # If no provider succeeded:
        raise RuntimeError(f"All providers failed or insufficient tier. Details: {errors}")

    def _log_routing(self, intent: CompletionIntent, result: CompletionResult):
        # Optional: write to DB/audit log
        print(
            f"[router] logical_model={intent.logical_model} "
            f"min_tier={intent.min_tier} -> {result.provider_name} / {result.actual_model}"
        )

3.2. Wiring it all together
Somewhere in your app startup:
header_store = HeaderStore("/etc/g4f/gemini_headers.json")
cookie_store = CookieStore("/etc/g4f/gemini_cookies.json")
gemini_session = GeminiWebSession(header_store, cookie_store)
gemini_provider = GeminiWebProvider(gemini_session)

deepseek_provider = DeepSeekProvider(...)   # you already have this
other_provider = SomeOtherProvider(...)

router = ModelRouter(
    providers=[
        gemini_provider,
        deepseek_provider,
        other_provider,
    ]
)

And for an incoming OpenAI-style request like:
def handle_chat_completions(req_json: Dict[str, Any]) -> Dict[str, Any]:
    logical_model = req_json["model"]          # e.g. "gpt-4"
    messages = req_json["messages"]

    # Translate logical model → required tier
    if logical_model in {"gpt-4", "gpt-4.1"}:
        min_tier = ModelTier.GEMINI_PRO
    else:
        min_tier = ModelTier.GEMINI_FLASH

    intent = CompletionIntent(
        logical_model=logical_model,
        min_tier=min_tier,
        messages=messages,
    )

    result = router.route(intent)

    # Map back to OpenAI-style response
    return {
        "id": "chatcmpl-xyz",
        "object": "chat.completion",
        "model": result.actual_model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result.content,
                },
                "finish_reason": "stop",
            }
        ],
        "provider": result.provider_name,            # optional extra
        "usage": {},                                 # fill if you can
    }


4. Where your Gemini Pro account actually comes in
With this architecture:
You sign into Gemini Pro in Chrome.


You export cookies + headers from that signed-in session into the CookieStore and HeaderStore.


GeminiWebSession behaves effectively like a “headless version of that exact browser”.


The backend decides “this account has Pro → route to Pro model”.


GeminiWebProvider detects that via _detect_tier_from_response and reports it as gemini-2.5-pro to the router.


No forced model hashes, no entitlement bypass — just clean automation of your own Pro session plus a router that knows when it really got Pro and when it didn’t.
If you’d like, next I can help you sketch:
What the extract_snlm0e_from_html and extract_text_from_response helpers might look like in a more concrete way (still abstracting away undocumented internals).



