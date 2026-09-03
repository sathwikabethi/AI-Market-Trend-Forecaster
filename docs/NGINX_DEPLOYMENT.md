# Nginx Deployment (Single Domain)

This project can be hosted behind Nginx on a VM/container host (recommended for the current backend design since it runs long-lived schedulers/workers).

The recommended topology is a single domain:
- `https://example.com` serves the built React frontend
- `https://example.com/api/*` proxies to the FastAPI backend

This avoids CORS and cross-domain cookie issues.

## 1) Build the Frontend
From the repo root:
```bash
cd frontend
npm ci
npm run build
```

Copy the build output to your server, e.g.:
- local path: `frontend/dist/`
- server path (used in the sample config): `/var/www/caresense/`

## 2) Run the Backend
Run uvicorn behind Nginx on localhost (or a private network interface):
```bash
python -m uvicorn src.api.main:app --host 127.0.0.1 --port 8002 --proxy-headers
```

Suggested production env vars:
- `AUTH_COOKIE_SECURE=1`
- `AUTH_COOKIE_SAMESITE=lax`
- `CORS_ORIGINS=https://example.com`
- `HF_LOCAL_FILES_ONLY=1` (or `0` if you want online model downloads)

## 3) Configure Nginx
Use the template:
- `deploy/nginx/caresense.conf`

Key settings:
- `root /var/www/caresense;` for SPA static files
- `location /api/ { proxy_pass http://127.0.0.1:8002/; }` for backend routes

## 4) TLS (Certbot)
On Ubuntu/Debian, you can use certbot:
```bash
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d example.com
```

After issuing the cert, update the domain + TLS paths in `deploy/nginx/caresense.conf` and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

