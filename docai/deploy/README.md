# DocAI v2 Lean Deploy (Single VM)

## 1) Backend virtualenv and install

```bash
cd /opt/docai
python3 -m venv /opt/docai/.venv
/opt/docai/.venv/bin/python -m pip install --upgrade pip
/opt/docai/.venv/bin/python -m pip install -r requirements.txt
```

## 2) Frontend build

Set backend API to nginx proxy path (`/api`) at build time.

```bash
cd /opt/docai/frontend
export VITE_DOCAI_API_BASE_URL=/api
npm ci
npm run lint
npm run build
```

## 3) Backend env file

```bash
sudo mkdir -p /etc/docai
sudo cp /opt/docai/deploy/.env.backend.example /etc/docai/docai-backend.env
# edit values for your host
```

## 4) systemd service

```bash
sudo cp /opt/docai/deploy/systemd/docai-backend.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now docai-backend
sudo systemctl status docai-backend --no-pager
```

## 5) nginx config

```bash
sudo cp /opt/docai/deploy/nginx/docai.conf /etc/nginx/sites-available/docai
sudo ln -sf /etc/nginx/sites-available/docai /etc/nginx/sites-enabled/docai
sudo nginx -t
sudo systemctl reload nginx
```

## 6) Health check

```bash
curl -sS http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"docai-v2-api"}
```

## 7) Smoke path

- Open frontend URL.
- Create Project.
- Create Job via NewJobPage.
- Upload one small document.
- Create Run.
- Attach document.
- Execute run.
- Open JobViewerPage and verify job/document/run metadata rows.

## Notes

- Current runtime still supports stub execution paths (`is_stub: true` in execute response).
- Persist `DOCAI_RUNS_DIR` and `DOCAI_SQLITE_PATH` directories.
- Keep backend bound to 127.0.0.1; expose through nginx.
- This scaffold is HTTP + no-auth by design for lean internal/demo use only; do not use for sensitive documents until TLS and access controls are added.
