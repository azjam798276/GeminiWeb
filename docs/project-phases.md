Phase 1: The Active "Hydra" Store
Problem: Your architecture assumes cookies in gemini_cookies.json stay valid. They won't. Solution: The Store must be "alive." It uses nodriver (from the Research) to refresh them when they die.
Python
import json
import os
import asyncio
from typing import Dict, Optional
# pip install nodriver
import nodriver as uc 

class HydraCookieStore:
    """
    Realizes the 'CookieStore' abstraction from your Architecture.
    But instead of just reading, it self-heals using the Hydra technique.
    """
    def __init__(self, path: str = "gemini_cookies.json", profile_dir: str = "./browser_profile"):
        self.path = path
        self.profile_dir = profile_dir
        self._cache = None

    def get_cookies(self) -> Dict[str, str]:
        # 1. Try Memory/Disk
        if not self._cache and os.path.exists(self.path):
            with open(self.path, 'r') as f:
                self._cache = json.load(f)
        
        # 2. Return what we have (Validation happens in Session)
        return self._cache or {}

    async def refresh_cookies(self):
        """The Hydra Loop: Launches Headless Chrome to satisfy DBSC."""
        print("[Hydra] Cookies expired. Launching browser for DBSC signature...")
        
        # We use a persistent profile so we don't have to 2FA every time
        browser = await uc.start(headless=True, user_data_dir=self.profile_dir)
        page = await browser.get("https://gemini.google.com")
        await page.wait_for("body")
        
        # Harvest fresh, cryptographically bound cookies
        cookies_list = await browser.cookies.get_all()
        # Filter for Google/Gemini cookies
        cookie_dict = {c.name: c.value for c in cookies_list if "google" in c.domain or "gemini" in c.domain}
        
        if "__Secure-1PSID" not in cookie_dict:
            print("[Hydra] CRITICAL: Login required. Run with headless=False once.")
        
        # Persist
        with open(self.path, 'w') as f:
            json.dump(cookie_dict, f)
        self._cache = cookie_dict
        
        await browser.stop()
        print("[Hydra] Session refreshed.")

Phase 2: The GeminiWebSession (The "Gel" Point)
Problem: Your architecture uses generic http. Solution: We inject the PoC's curl_cffi and batchexecute logic here.
Python
import re
import json
import random
# pip install curl_cffi
from curl_cffi.requests import AsyncSession

class GeminiWebSession:
    def __init__(self, header_store, cookie_store: HydraCookieStore):
        self.cookie_store = cookie_store
        # We discard HeaderStore for User-Agent because curl_cffi handles it dynamically
        self._snlm0e = None
        
        # MIT RESEARCH ARTIFACT: TLS Immunity
        # We must mimic Chrome 120 to pass the gateway
        self.session_args = {"impersonate": "chrome120"}

    async def _get_snlm0e(self, session):
        # Implementation of PoC's regex scraping
        resp = await session.get("https://gemini.google.com/app")
        match = re.search(r'SNlM0e":"(.*?)"', resp.text)
        return match.group(1) if match else None

    async def call_chat_endpoint(self, payload: dict, intent_tier: str, retry=True):
        cookies = self.cookie_store.get_cookies()
        
        headers = {
            "Accept": "*/*",
            "Origin": "https://gemini.google.com",
            "X-Same-Domain": "1", # Critical for Google AJAX
        }

        # --- THE POC ROUTING LOGIC (Optional) ---
        # If we explicitly want Pro, we can inject the PoC hash as a safety net.
        # This prevents "Nano Banana Fallback" during high load.
        if intent_tier == "gemini-2.5-pro":
             # 525001261 is the Model Config Extension ID
             headers["X-Goog-Ext-525001261-Jspb"] = '[1,null,null,null,"61530e79959ab139",null,null,null,]'
        
        async with AsyncSession(cookies=cookies, headers=headers, **self.session_args) as s:
            # 1. Bootstrap SNlM0e
            if not self._snlm0e:
                self._snlm0e = await self._get_snlm0e(s)
                if not self._snlm0e:
                     # If we can't get token, cookies are dead -> Hydra Refresh
                    if retry:
                        await self.cookie_store.refresh_cookies()
                        return await self.call_chat_endpoint(payload, intent_tier, retry=False)
                    raise RuntimeError("DBSC Failure / Session Dead")

            # 2. Serialize Protocol (The Batchexecute Envelope)
            # The Architecture passed a dict; we must wrap it in f.req
            data = {
                "f.req": json.dumps([[[ "XqA3Ic", json.dumps(payload), None, "generic" ]]]),
                "at": self._snlm0e
            }
            
            # 3. Execute
            resp = await s.post(
                "https://gemini.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate",
                data=data,
                params={"bl": "boq_assistant-bard-web-server_20240519.16_p0", "_reqid": str(random.randint(1000,9999)), "rt": "c"}
            )
            
            if resp.status_code in [401, 403]:
                if retry:
                    await self.cookie_store.refresh_cookies()
                    return await self.call_chat_endpoint(payload, intent_tier, retry=False)
            
            return resp.text

Phase 3: The Provider (Payload Synthesis)
Problem: Your architecture needs to convert OpenAI messages to Gemini's internal array. Solution: Use the structure reversed in the PoC.
Python
class GeminiWebProvider:
    # ... init ...
    
    def _intent_to_payload(self, intent):
        prompt = intent.messages[-1]["content"]
        
        # MIT RESEARCH ARTIFACT: The Internal JSON Structure
        # We explicitly set flag [1] to request "Thinking" (Pro feature)
        # This matches the PoC's discovery.
        return [
            [prompt, 0, None, [], None, None, 0],
            ["en"],
            [f"cid_{random.randint(100,999)}", "", ""],
            "", None, None, 
            [1], # <--- Feature Flag: Request Pro/Thinking
            0, [], None, 1, 0
        ]

    async def complete(self, intent):
        # 1. Build Payload
        inner_payload = self._intent_to_payload(intent)
        
        # 2. Execute (with optional forced injection if tier is Pro)
        raw_resp = await self.session.call_chat_endpoint(inner_payload, intent.min_tier)
        
        # 3. Detect Tier (Architecture Logic)
        # Check if the response actually contains "Thinking" blocks
        actual_tier = "gemini-2.5-pro" if "Thinking" in raw_resp or len(raw_resp) > 2000 else "gemini-flash"
        
        return CompletionResult(..., tier=actual_tier)

3. Final Recommendation
The GeminiWeb Architecture is the correct "Body" for your system, but it relies on the PoC to act as the "Brain" and "Nerves."
Adopt the Architecture's Class Structure. It is cleaner and scales to multiple providers.
Gut the internals of GeminiWebSession and replace them with the PoC's curl_cffi implementation.
Upgrade the CookieStore to use the nodriver logic (Hydra) to handle the DBSC refresh, otherwise, your architecture will stop working after 15 minutes.
Use the PoC's [1] JSON flag in the payload to naturally trigger the Pro model features (Thinking) without needing the aggressive X-Goog-Jspb injection (unless Google starts downgrading you, in which case, re-enable the injection as a fallback).

