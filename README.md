# Ledger Agent Server

Public HTTPS endpoint that answers plain-English questions about your private Acme Appliances order ledger.

- `POST /ask` with `{"question": "..."}` → `{"answer": ...}`
- Loads `/export` + `/rates` from your signed exam API at startup
- Dedupes by latest `updated_at`, converts to USD, uses Asia/Kolkata business dates
- Only `paid` orders count as revenue

Registered email: `23f1001613@ds.study.iitm.ac.in`

## Local run

```powershell
cd d:\projects\gagan_project\ledger-agent-server
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

In another terminal:

```powershell
cd d:\projects\gagan_project\ledger-agent-server
.\.venv\Scripts\activate
python test_local.py
```

- Ask: `http://127.0.0.1:8080/ask`
- Health: `http://127.0.0.1:8080/health`

Quick manual check:

```powershell
curl -Method POST -Uri http://127.0.0.1:8080/ask -ContentType application/json -Body '{"question":"What was the total revenue in USD from the North region in March 2026?"}'
```

## Push to GitHub (you do this)

```powershell
cd d:\projects\gagan_project\ledger-agent-server

git init
git add app.py ledger.py qa.py requirements.txt render.yaml test_local.py README.md .gitignore
git commit -m "Add Acme ledger Q&A agent server"

git branch -M main
```

Create an empty GitHub repo (no README), then:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```

Or with GitHub CLI:

```powershell
gh repo create YOUR_REPO_NAME --private --source=. --remote=origin --push
```

## Deploy on Render (you do this)

1. Go to [https://dashboard.render.com](https://dashboard.render.com)
2. **New** → **Blueprint**
3. Connect the GitHub repo you just pushed
4. Render reads `render.yaml` and deploys `ledger-agent-server`
5. Wait until the service is live (first boot fetches the ledger)

### Manual Web Service (if not using Blueprint)

- Runtime: Python
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

## What URL to paste in the exam form

The form says “public MCP endpoint URL”. For this question, paste your **ask** URL:

```text
https://<your-service-name>.onrender.com/ask
```

Example:

```text
https://ledger-agent-server.onrender.com/ask
```

Before submitting, verify:

```powershell
Invoke-RestMethod -Method GET https://<your-service-name>.onrender.com/health
Invoke-RestMethod -Method POST https://<your-service-name>.onrender.com/ask -ContentType 'application/json' -Body '{"question":"What was the total revenue in USD from the North region in March 2026?"}'
```

## Keep it awake through grading

Render free instances sleep when idle. Hit `/health` every 5–10 minutes (UptimeRobot or similar) until the grading deadline so live checks do not time out.

## After a code fix: push and redeploy

```powershell
cd d:\projects\gagan_project\ledger-agent-server
git add qa.py test_local.py README.md
git commit -m "Count distinct customers for how-many-customers questions"
git push
```

Wait for Render to finish deploying, then verify:

```powershell
Invoke-RestMethod -Method POST https://ledger-agent-server-gazy.onrender.com/ask -ContentType 'application/json' -Body '{"question":"How many different customers placed at least one paid order for a Toaster?"}'
```

Expect `answer` = `206`. Then resubmit the same URL in the exam form.
