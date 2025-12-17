Technical Design Document v0.1: GeminiWebProvider Integration
Date: 2025-12-07
Status: Draft / POC
Authors: Senior Backend Engineering Team

1. Overview
1.1 Problem Statement
Current "free" providers in the gpt4free stack suffer from reliability issues, aggressive rate limiting, and low-quality model output (often defaulting to the smallest "Flash" or "Nano" tiers). While users may possess legitimate Gemini Pro entitlements via their personal Google accounts, there is no unified interface to leverage these entitlements programmatically alongside other providers in an OpenAI-compatible manner. Furthermore, static cookie exports fail rapidly (often <15 minutes) due to session rotation1.
1.2 Goals
Unified Interface: Expose the Gemini web client as a standard Provider within the existing architecture.
Session Continuity: Implement a "Hydra" self-healing mechanism to refresh authentication cookies automatically using a headless browser2.
Tier Transparency: Detect the actual model used for inference (e.g., differentiating gemini-2.5-flash from gemini-2.5-pro) and expose this to the routing layer3.
TLS Immunity: utilize curl_cffi to mimic Chrome 120+ fingerprints, bypassing standard bot detection at the edge4.
1.3 Non-Goals
No Entitlement Bypass: This POC will not attempt to inject headers (e.g., X-Goog-Jspb) to force-enable Pro models on accounts that do not have them. We rely strictly on the account's server-side standing5.
No Billing Bypass: We do not attempt to bypass quotas or legitimate rate limits imposed by Google on the authenticated account.

2. Scope & Assumptions
2.1 Scope
Implementation of HydraCookieStore for cookie management.
Implementation of GeminiWebSession for batchexecute protocol handling.
Implementation of GeminiWebProvider for payload translation.
Implementation of a rudimentary ModelRouter for tier-based fallback.
2.2 Assumptions
Environment: The system runs in a Linux environment capable of spawning processes (required for nodriver/Chrome)6.
Account: The user provides a browser_profile or initial gemini_cookies.json from a valid Google account with Gemini Advanced entitlements7.
Stack: Existing gpt4free infrastructure is available for plugging in the new provider class.

3. High-Level Architecture
The system treats GeminiWeb as a volatile but high-quality provider that requires "living" session management.
Code snippet
graph TD
    Client[Client (OpenAI API)] --> Router[ModelRouter]
    
    subgraph "Routing Layer"
        Router -->|Intent: MinTier=Pro| GWP[GeminiWebProvider]
        Router -->|Fallback| DSP[DeepSeekProvider]
    end

    subgraph "Gemini Integration"
        GWP -->|Payload| Session[GeminiWebSession]
        Session -->|Get Cookies| Hydra[HydraCookieStore]
        
        Hydra -.->|Refresh Loop| Headless[Headless Chrome (nodriver)]
        Headless -.->|Login/Sign| GoogleAuth[Google Accounts]
        
        Session -->|RPC: StreamGenerate| GFE[Google Front End]
    end


Data Flow
Intent: Router receives a request for gpt-4 (mapped to GEMINI_PRO).
Dispatch: Router selects GeminiWebProvider.
Auth: Provider requests session; HydraCookieStore verifies cookie validity. If expired, it launches nodriver to refresh credentials8.
Transport: GeminiWebSession wraps the prompt in the batchexecute envelope, ensuring curl_cffi impersonates Chrome 1209.
Detection: Response is parsed; Provider inspects metadata/content to determine if the result is truly Pro (e.g., presence of "Thinking" blocks)10.
Verification: Router compares ActualTier vs RequestedTier. If sufficient, returns result. If not (e.g., downgrade to Flash), logs "Soft Fail" and triggers fallback.

4. Key Components
4.1 HydraCookieStore
Purpose: Realizes the "CookieStore" abstraction but adds the "alive" property to solve the expiration problem11.
Responsibility:
Hold gemini_cookies.json in memory.
Check validity before serving.
The Hydra Loop: If cookies are rejected (401/403) or missing, launch nodriver (headless Chrome), navigate to gemini.google.com, wait for idle, and harvest fresh __Secure-1PSID cookies12.
Interface:
get_cookies() -> Dict[str, str]
refresh_cookies() -> Coroutine 13
4.2 GeminiWebSession
Purpose: Manages the low-level HTTP/RPC conversation with Google's consumer edge.
Dependencies: curl_cffi (for TLS fingerprinting), HydraCookieStore.
Key Methods:
_get_snlm0e(session): Scrapes the specific anti-XSRF token from the HTML14.
call_chat_endpoint(payload, intent_tier):
Constructs the f.req envelope: [[["XqA3Ic", json_payload, null, "generic"]]]15.
Injects headers: X-Same-Domain: 1 (Critical for AJAX)16.
Executes POST to /_/BardChatUi/.../StreamGenerate17.
Error Handling:
On HTTP 401/403: Trigger store.refresh_cookies() and retry once18.
On "Session Dead": Raise explicit error to trigger Router fallback.
4.3 GeminiWebProvider
Purpose: Translates OpenAI intent to Gemini payload and normalizes the response.
Payload Synthesis:
Maps intent.messages[-1] to the prompt slot.
Feature Flagging: Uses the internal JSON flag [1] in the payload (index 7 or similar in the array) to request Pro features like "Thinking" if the intent requires it19. This is a request, not a force; the server decides based on entitlements.
Tier Detection (_detect_tier_from_response):
Inspects raw response text.
Heuristic: If response contains "Thinking" process blocks or exceeds specific token density, mark as GEMINI_PRO. Otherwise, default to GEMINI_FLASH20.
Note: This relies on the observation that the "Thinking" feature is currently exclusive to the Pro tier.
4.4 ModelRouter
Purpose: Orchestrates reliability.
Logic:
Lookup intent.logical_model (e.g., "gpt-4") → RequiredTier (e.g., GEMINI_PRO).
Iterate through providers.
If GeminiWebProvider returns GEMINI_FLASH but RequiredTier is GEMINI_PRO:
Log Routing Drift (Requested Pro, got Flash).
Discard result (or mark as degraded) and try next provider (e.g., DeepSeek)21.

5. Data Models & Interfaces
5.1 Enums & Dataclasses
Python
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

class ModelTier(str, Enum):
    GEMINI_FLASH = "gemini-2.5-flash"  # Low tier / Fallback
    GEMINI_PRO = "gemini-2.5-pro"      # High tier / Thinking
    GEMINI_ANY = "gemini-any"

@dataclass
class CompletionIntent:
    logical_model: str          # "gpt-4"
    min_tier: ModelTier         # GEMINI_PRO
    messages: List[Dict[str, str]]

@dataclass
class CompletionResult:
    provider_name: str          # "GeminiWeb"
    actual_model: str           # "gemini-2.5-flash"
    tier: ModelTier             # Normalized tier
    content: str
    raw_response: Any = None


5.2 Interfaces
Python
class GeminiWebProvider:
    async def complete(self, intent: CompletionIntent) -> CompletionResult:
        # 1. Build Payload (requesting Pro features if needed)
        # 2. Execute via Session
        # 3. Detect Tier
        # 4. Return Result
        pass

class ModelRouter:
    async def route(self, intent: CompletionIntent) -> CompletionResult:
        # Iterate providers -> check result.tier >= intent.min_tier
        pass



6. Sequence Diagrams
6.1 Happy Path (Pro Entitlement Active)
User -> Router: Request "gpt-4"
Router -> GeminiWebProvider: Intent(min_tier=PRO)
GeminiWebProvider -> GeminiWebSession: POST (Payload w/ Flag [1])
GeminiWebSession -> Google: StreamGenerate (Cookie: ProAccount)
Google -> GeminiWebSession: 200 OK (Contains "Thinking" blocks)
GeminiWebSession -> GeminiWebProvider: Raw JSON
GeminiWebProvider -> GeminiWebProvider: detect_tier() -> PRO
GeminiWebProvider -> Router: Result(tier=PRO)
Router -> User: 200 OK (Content)


6.2 Degraded Path (Account Downgraded/Limited)
User -> Router: Request "gpt-4"
Router -> GeminiWebProvider: Intent(min_tier=PRO)
GeminiWebProvider -> GeminiWebSession: POST (Payload w/ Flag [1])
GeminiWebSession -> Google: StreamGenerate (Cookie: FreeAccount/QuotaLimit)
Google -> GeminiWebSession: 200 OK (Standard Flash response, no Thinking)
GeminiWebProvider -> GeminiWebProvider: detect_tier() -> FLASH
GeminiWebProvider -> Router: Result(tier=FLASH)
Router -> Router: Tier Mismatch (FLASH < PRO) -> Log Warning
Router -> DeepSeekProvider: Intent(min_tier=PRO)
DeepSeekProvider -> Router: Result(tier=PRO)
Router -> User: 200 OK (DeepSeek Content)



7. Security & Compliance
Credential Isolation: gemini_cookies.json and the browser_profile directory contain sensitive session tokens. These must be stored with restricted file permissions (600) and never committed to version control.
Behavioral Mirroring: The strictly defined scope ensures we behave like a user: we log in, we send a message, we read the response. We do not fuzz headers or inject disallowed X-Goog-Jspb extensions to spoof entitlements22.
Rate Limiting: The POC will implement a simple "cool-down" if 429s are detected, defaulting to other providers to avoid flagging the Google account.

8. Operational Concerns (POC)
Configuration:
COOKIE_PATH: Path to gemini_cookies.json.
PROFILE_PATH: Path to Chrome user data dir (for nodriver persistence).
Observability:
Log [Hydra] events: "Cookies expired", "Browser launching", "Session refreshed".
Log [Router] events: "Tier Drift detected: Expected Pro, got Flash".
Failure Modes:
If nodriver fails to launch (headless environment issues), HydraCookieStore must raise a critical exception, causing the Router to permanently disable GeminiWebProvider for the process lifetime.

9. Risks & Next Steps
Protocol Volatility: The f.req structure and SNlM0e scraping logic are brittle and may break with UI updates. v0.2 should implement dynamic parsing of the batchexecute envelope.
Tier Detection Accuracy: Relying on "Thinking" blocks is a heuristic. Google may change how Pro features are serialized. v0.2 should explore decoding the response metadata (Protobuf analysis) for definitive model IDs.
Next Step: Implement the HydraCookieStore logic first, as without reliable cookies, the provider is useless. Verify nodriver works in the target deployment environment (e.g., Docker container constraints).

