import html as html_lib
import os
import smtplib
import logging
import time
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Lock
from typing import List, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="shaheer.dev API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://shaheer.dev", "https://www.shaheer.dev"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


# ── SECURITY HEADERS ──

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ── BOT UA BLOCKLIST ── (added last = runs first / outermost)

_BOT_UA_FRAGMENTS = [
    "python-requests", "python-httpx", "python-urllib",
    "curl/", "wget/", "scrapy/", "go-http-client",
    "libwww-perl", "java/", "okhttp", "httpie", "axios/",
]

@app.middleware("http")
async def block_bots(request: Request, call_next):
    ua = request.headers.get("user-agent", "").lower()
    if any(frag in ua for frag in _BOT_UA_FRAGMENTS):
        return Response("Forbidden", status_code=403)
    return await call_next(request)


# ── RATE LIMITER ──

_rate_data: dict[str, list[float]] = defaultdict(list)
_rate_lock = Lock()

def _check_rate(key: str, max_calls: int, window_secs: int) -> bool:
    """Sliding-window rate limiter. Returns True if the request is allowed."""
    now = time.time()
    with _rate_lock:
        calls = _rate_data[key]
        calls[:] = [t for t in calls if now - t < window_secs]
        if len(calls) >= max_calls:
            return False
        calls.append(now)
        if len(_rate_data) > 20000:
            stale = [k for k, v in list(_rate_data.items()) if not v][:2000]
            for k in stale:
                del _rate_data[k]
        return True

_interval_data: dict[str, float] = {}
_interval_lock = Lock()

def _check_interval(key: str, min_secs: float) -> bool:
    """Returns True if enough time has passed since last call from this IP."""
    now = time.time()
    with _interval_lock:
        last = _interval_data.get(key, 0.0)
        if now - last < min_secs:
            return False
        _interval_data[key] = now
        if len(_interval_data) > 10000:
            cutoff = now - 120
            stale = [k for k, v in list(_interval_data.items()) if v < cutoff][:2000]
            for k in stale:
                del _interval_data[k]
        return True

def _client_ip(request: Request) -> str:
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf.strip()
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.zoho.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASS      = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", "shaheer@shaheer.dev")

NEXADESK_DEMO_PROMPT = """
You are Nadia, the AI receptionist for Prestige Properties — a premium Gulf real estate agency.

PROPERTY LISTINGS (your knowledge base):
- Downtown Dubai: 2BR luxury apartment, AED 2.8M, direct Burj Khalifa view, ready to move in
- Dubai Marina: 1BR with full sea view, AED 1.5M, high floor, Q3 2025 handover
- Palm Jumeirah: 4BR beachfront villa, AED 12M, private pool and beach, fully furnished
- Abu Dhabi (Al Reem Island): 3BR waterfront apartment, AED 1.9M, off-plan, 10% down payment
- Sharjah (Al Zahia): 2BR townhouse, AED 750K, gated family community, near international schools

YOUR GOALS (in order):
1. Understand what the visitor is looking for — ask 1–2 good questions, don't rush
2. Match them to a listing above, or offer to have an agent follow up with more options
3. Collect: name, phone number, and optionally email
4. Once you have name + contact: "Perfect — I'll make sure our team reaches you within 2 hours."

RULES:
- 2–3 sentences per reply maximum. Never write paragraphs.
- Warm and professional — Gulf hospitality standard
- Respond in whatever language the visitor uses: English, Arabic, or Urdu
- If asked about a property NOT in your listings, say you'll check and ask for their contact details
- Never invent prices, availability, or features beyond what's listed above
""".strip()

SYSTEM_PROMPT = """
You are the AI receptionist on shaheer.dev — the portfolio of Shaheer Salal's AI product studio.

Your name is "Shaheer's Assistant."

OPENING — say this gracefully in your very first message:
Greet the visitor warmly. Within the first 2 sentences, tell them:
"By the way — this conversation is a live demo of what we build. AI receptionists exactly like me, deployed for real estate agencies and accounting firms, qualifying leads and answering questions around the clock. You're experiencing the product right now."

Then ask what brought them here.

YOUR GOALS (in order):
1. Understand their problem — ask 1–2 good clarifying questions, don't rush
2. Position Shaheer's work as the natural solution (NexaDesk for lead/reception problems, AskTax for tax/document problems, custom builds for everything else)
3. Collect: name, email, company or project name, rough budget (optional), timeline (optional)
4. Once name + email collected: "Perfect — I'll make sure Shaheer gets your details. Expect to hear from him within 24 hours."

SHAHEER'S PRODUCTS:
- NexaDesk: 9-agent AI receptionist for Gulf real estate agencies and US property management. Handles WhatsApp + voice, qualifies leads, books viewings 24/7. AED 1,300 setup + AED 300/month.
- AskTax.pk: RAG SaaS for Pakistani CA firms. 195K+ FBR vectors, 4,491 documents, 2,041 case laws. Paying clients.
- Custom AI builds: FastAPI, Docker, RAG pipelines, multi-agent workflows, automation.

RULES:
- Respond in whatever language the visitor writes in — English, Arabic, Urdu all supported
- 2–4 sentences max per turn — never write paragraphs
- Warm, confident, intelligent — like a sharp human receptionist who knows the business
- Never be pushy. Never pitch before understanding.
- If asked technical questions about Shaheer's work, answer them — you know the stack
""".strip()


# ── MODELS ──

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=10000)

class ChatRequest(BaseModel):
    messages: List[Message] = Field(..., min_length=1, max_length=50)

class NotifyRequest(BaseModel):
    name:       str = Field(...,  max_length=200)
    email:      str = Field(...,  max_length=200)
    company:    str = Field("",   max_length=200)
    budget:     str = Field("",   max_length=100)
    timeline:   str = Field("",   max_length=100)
    transcript: str = Field("",   max_length=50000)


# ── ENDPOINTS ──

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/nexadesk-demo")
async def nexadesk_demo(req: ChatRequest, request: Request):
    ip = _client_ip(request)
    if not _check_rate(f"nd:{ip}", max_calls=15, window_secs=600):
        return {"reply": "Demo is busy right now — please try again in a few minutes."}
    if not _check_interval(f"nd_iv:{ip}", min_secs=3):
        return {"reply": "Please wait a moment before sending another message."}

    messages = [{"role": "system", "content": NEXADESK_DEMO_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
                "max_tokens": 200,
                "temperature": 0.45,
            },
        )
        resp.raise_for_status()

    reply = resp.json()["choices"][0]["message"]["content"].strip()
    return {"reply": reply}


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    ip = _client_ip(request)
    if not _check_rate(f"chat:{ip}", max_calls=20, window_secs=600):
        return {"reply": "I'm getting a lot of messages right now — please wait a moment and try again."}
    if not _check_interval(f"chat_iv:{ip}", min_secs=3):
        return {"reply": "Please wait a moment before sending another message."}

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": "gpt-4o-mini",
                "messages": messages,
                "max_tokens": 300,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()

    reply = resp.json()["choices"][0]["message"]["content"].strip()
    return {"reply": reply}


@app.post("/notify")
async def notify(req: NotifyRequest, request: Request):
    if not _check_rate(f"notify:{_client_ip(request)}", max_calls=3, window_secs=3600):
        return {"success": False}

    def esc(v: str) -> str:
        return html_lib.escape(v)

    try:
        body = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#111">
          <h2 style="color:#4f8ef7;border-bottom:2px solid #4f8ef7;padding-bottom:8px">
            🔥 New Lead from shaheer.dev
          </h2>
          <table style="width:100%;border-collapse:collapse;margin:16px 0">
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600;width:120px">Name</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{esc(req.name)}</td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Email</td>
              <td style="padding:10px;border-bottom:1px solid #eee">
                <a href="mailto:{esc(req.email)}">{esc(req.email)}</a>
              </td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Company</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{esc(req.company) or '—'}</td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Budget</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{esc(req.budget) or '—'}</td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Timeline</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{esc(req.timeline) or '—'}</td>
            </tr>
          </table>
          <h3 style="color:#555;margin-top:24px">Conversation Transcript</h3>
          <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;
                      padding:16px;font-size:13px;white-space:pre-wrap;line-height:1.65">
{esc(req.transcript)}
          </div>
          <p style="color:#aaa;font-size:12px;margin-top:24px">
            Sent automatically by the AI receptionist on shaheer.dev
          </p>
        </body></html>
        """

        safe_name = req.name.replace("\n", "").replace("\r", "")
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔥 New Lead from shaheer.dev — {safe_name}"
        msg["From"]    = SMTP_USER
        msg["To"]      = NOTIFY_EMAIL
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        return {"success": True}

    except Exception as e:
        logger.error(f"/notify failed: {e}")
        return {"success": False}
