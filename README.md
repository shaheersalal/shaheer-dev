# shaheer.dev

Personal site and AI product studio portfolio for Shaheer Salal.

---

## File structure

```
shaheer-dev/
├── index.html        # Complete single-page site (self-contained)
├── main.py           # FastAPI backend — /chat, /notify, /health
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md
```

| File | Where it runs |
|------|--------------|
| `index.html` | Any static host — Cloudflare Pages, GitHub Pages, Vercel, Netlify |
| `main.py` | VPS (DigitalOcean, Hetzner), Railway, or Docker container |

---

## Backend setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values — see field descriptions below.

### 3. Run locally

```bash
uvicorn main:app --reload --port 8000
```

API is now live at `http://localhost:8000`. Verify with:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Frontend — connecting to the backend

`index.html` has one line to change before going to production:

```js
// Near the bottom of the <script> block:
const API_BASE = 'http://localhost:8000'; // ← change this
```

Set it to your deployed backend URL, e.g. `https://api.shaheer.dev`.

---

## Zoho SMTP setup

The `/notify` endpoint sends lead emails via Zoho Mail.

1. Log into Zoho Mail → **Settings → Security → App Passwords**
2. Create a new app password (label it "shaheer.dev")
3. Copy the generated password into `.env` as `SMTP_PASS`

`.env` values for Zoho:

```
SMTP_HOST=smtp.zoho.com
SMTP_PORT=587
SMTP_USER=shaheer@shaheer.dev
SMTP_PASS=<app-password-from-zoho>
NOTIFY_EMAIL=shaheer@shaheer.dev
```

> Use the **app password**, not your Zoho account password. SMTP with `STARTTLS` on port 587.

---

## Deployment options

### Option A — Railway (recommended, one-click)

1. Push this repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Select the repo — Railway auto-detects FastAPI
4. Add environment variables in the Railway dashboard (copy from `.env`)
5. Railway gives you a public URL — paste it into `API_BASE` in `index.html`

### Option B — VPS with nginx reverse proxy

```bash
# On your server
git clone https://github.com/shaheersalal/shaheer-dev
cd shaheer-dev
pip install -r requirements.txt
cp .env.example .env && nano .env

# Run with uvicorn (use a process manager like systemd or supervisor in production)
uvicorn main:app --host 127.0.0.1 --port 8000
```

nginx config (`/etc/nginx/sites-available/api.shaheer.dev`):

```nginx
server {
    listen 443 ssl;
    server_name api.shaheer.dev;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/api.shaheer.dev /etc/nginx/sites-enabled/
sudo certbot --nginx -d api.shaheer.dev
sudo nginx -s reload
```

### Option C — Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY main.py .env ./
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t shaheer-api .
docker run -p 8000:8000 --env-file .env shaheer-api
```

---

## CORS

`main.py` currently allows all origins (`allow_origins=["*"]`).

Before going live, restrict this to your domain:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://shaheer.dev", "https://www.shaheer.dev"],
    ...
)
```

---

## Environment variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI API key — get from platform.openai.com |
| `SMTP_HOST` | Zoho SMTP host — `smtp.zoho.com` |
| `SMTP_PORT` | SMTP port — `587` (STARTTLS) |
| `SMTP_USER` | Your Zoho email — `shaheer@shaheer.dev` |
| `SMTP_PASS` | Zoho **app password** (not your login password) |
| `NOTIFY_EMAIL` | Where lead notifications are sent |
