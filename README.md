# Instantly.ai Campaign Dashboard

Web UI for managing Instantly.ai email campaigns.

## Features

- View campaign statistics in real-time
- Browse and filter leads (Clinic leads, All leads, Other leads)
- Start/pause campaigns
- Monitor active leads and pending leads
- HTTP Basic Auth protected

## Deployment

### Railway

1. Create new project from GitHub repo
2. Set environment variables:
   - `INSTANTLY_API_KEY` - Your Instantly.ai API key
   - `DASHBOARD_USERNAME` - Dashboard login username (default: admin)
   - `DASHBOARD_PASSWORD` - Dashboard login password (default: changeme)
3. Deploy

### Local Development

```bash
pip install -r requirements.txt
export INSTANTLY_API_KEY="your-key"
export DASHBOARD_USERNAME="admin"
export DASHBOARD_PASSWORD="changeme"
python3 app.py
```

Open http://localhost:5001

## Campaign

Current campaign: **WA Integrative Medicine**
- Campaign ID: bfe30fd9-3417-410f-800b-7b8e7151a965
- 164 clinic leads ready to send
- Daily limit: 50 emails/day
