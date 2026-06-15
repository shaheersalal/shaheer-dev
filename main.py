import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="shaheer.dev API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://shaheer.dev", "https://www.shaheer.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.zoho.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASS      = os.getenv("SMTP_PASS", "")
NOTIFY_EMAIL   = os.getenv("NOTIFY_EMAIL", "shaheer@shaheer.dev")

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
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

class NotifyRequest(BaseModel):
    name: str
    email: str
    company: str = ""
    budget: str = ""
    timeline: str = ""
    transcript: str = ""


# ── ENDPOINTS ──

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/chat")
async def chat(req: ChatRequest):
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
async def notify(req: NotifyRequest):
    try:
        html = f"""
        <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#111">
          <h2 style="color:#4f8ef7;border-bottom:2px solid #4f8ef7;padding-bottom:8px">
            🔥 New Lead from shaheer.dev
          </h2>
          <table style="width:100%;border-collapse:collapse;margin:16px 0">
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600;width:120px">Name</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{req.name}</td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Email</td>
              <td style="padding:10px;border-bottom:1px solid #eee">
                <a href="mailto:{req.email}">{req.email}</a>
              </td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Company</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{req.company or '—'}</td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Budget</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{req.budget or '—'}</td>
            </tr>
            <tr>
              <td style="padding:10px;background:#f5f5f5;font-weight:600">Timeline</td>
              <td style="padding:10px;border-bottom:1px solid #eee">{req.timeline or '—'}</td>
            </tr>
          </table>
          <h3 style="color:#555;margin-top:24px">Conversation Transcript</h3>
          <div style="background:#f9f9f9;border:1px solid #ddd;border-radius:6px;
                      padding:16px;font-size:13px;white-space:pre-wrap;line-height:1.65">
{req.transcript}
          </div>
          <p style="color:#aaa;font-size:12px;margin-top:24px">
            Sent automatically by the AI receptionist on shaheer.dev
          </p>
        </body></html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔥 New Lead from shaheer.dev — {req.name}"
        msg["From"]    = SMTP_USER
        msg["To"]      = NOTIFY_EMAIL
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

        return {"success": True}

    except Exception as e:
        logger.error(f"/notify failed: {e}")
        return {"success": False}
