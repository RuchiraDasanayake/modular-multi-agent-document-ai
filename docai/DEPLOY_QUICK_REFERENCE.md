# DocAI Alpha - Deployment Quick Reference

**For Quick Deployment on Oracle Cloud VM**

## TL;DR - 5 Minutes Setup

```bash
# 1. SSH into Oracle VM
ssh ubuntu@<ORACLE_IP>

# 2. Update and install
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip git nginx tesseract-ocr nodejs npm ufw apache2-utils

# 3. Clone and setup
git clone <REPO_URL> /opt/docai
cd /opt/docai
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# 4. Build frontend
cd frontend
VITE_DOCAI_API_BASE_URL=/api npm run build
cd ..

# 5. Create data directories
sudo mkdir -p /var/lib/docai/{runs,uploads}
sudo useradd -s /bin/false -d /opt/docai docai
sudo chown -R docai:docai /opt/docai /var/lib/docai

# 6. Setup systemd
sudo cp deploy/docai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable docai
sudo systemctl start docai

# 7. Setup Nginx
sudo cp deploy/nginx.docai.conf /etc/nginx/sites-available/docai
sudo ln -s /etc/nginx/sites-available/docai /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t
sudo systemctl reload nginx

# 8. Setup Basic Auth
sudo htpasswd -c /etc/nginx/.docai_htpasswd alpha
# When prompted, enter password (e.g., "alpha123")

# Uncomment auth in Nginx config
sudo sed -i 's/# auth_basic/auth_basic/' /etc/nginx/sites-available/docai
sudo sed -i 's/# auth_basic_user_file/auth_basic_user_file/' /etc/nginx/sites-available/docai
sudo nginx -t && sudo systemctl reload nginx

# 9. Setup firewall
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable

# 10. Smoke test (from your laptop)
ORACLE_IP=<your-oracle-ip>
curl -u alpha:alpha123 http://$ORACLE_IP/api/health
# Should return: {"status":"ok","service":"docai-v2-api"}

# Open in browser: http://$ORACLE_IP/
# Login: alpha / alpha123
```

## Public URL Structure

```
http://<oracle-vm-public-ip>/              → Frontend (SPA)
http://<oracle-vm-public-ip>/api/          → Backend (reverse proxy)
http://<oracle-vm-public-ip>/api/health    → Health check
```

**Backend is NOT exposed directly on port 8000 (blocked by UFW)**

## Key Files

| File | Purpose | Location |
|------|---------|----------|
| `docai.service` | Systemd service (Type=simple for uvicorn) | `deploy/` |
| `nginx.docai.conf` | Nginx reverse proxy + auth + static | `deploy/` |
| `.env.production` | Frontend API base URL setting | `deploy/` |
| `DEPLOYMENT.md` | Full deployment guide | repo root |

## Service Management

```bash
# Check status
sudo systemctl status docai

# Restart
sudo systemctl restart docai

# View logs
sudo journalctl -u docai -f

# Reload Nginx
sudo systemctl reload nginx
```

## Troubleshooting One-Liners

```bash
# Is backend running?
curl http://127.0.0.1:8000/health

# Is Nginx reverse proxy working?
curl -u alpha:alpha123 http://127.0.0.1/api/health

# Check systemd service
sudo systemctl status docai

# Check Nginx config
sudo nginx -t

# Frontend built correctly?
ls -la /opt/docai/frontend/dist/

# Database exists?
ls -lh /var/lib/docai/docai.sqlite

# Firewall allows 80/443?
sudo ufw status | grep "80\|443"

# Check service logs
sudo journalctl -u docai -n 50
```

## Database Location

- **SQLite file**: `/var/lib/docai/docai.sqlite`
- **Run artifacts**: `/var/lib/docai/runs/`
- **Backups**: Create periodically with `sudo cp /var/lib/docai/docai.sqlite /opt/backups/docai.sqlite.YYYYMMDD`

## Security Checklist

- [ ] Backend bound to 127.0.0.1 (not 0.0.0.0)
- [ ] Port 8000 NOT open in UFW firewall
- [ ] Port 5173 NOT open in UFW firewall
- [ ] Only ports 22 (SSH), 80, 443 (Nginx) are open
- [ ] Basic Auth credentials set (not default)
- [ ] Nginx reverse proxy strips backend URL properly
- [ ] Frontend API base URL is `/api` not `http://127.0.0.1:8000`

## Common Issues

**Frontend shows blank page**
- Check browser console for network errors
- Verify API base URL: right-click → Inspect → Network tab → check /api/ calls
- Rebuild frontend: `cd frontend && npm run build`

**Upload fails**
- Check `/var/lib/docai/` has sufficient disk space
- Verify Nginx: `grep client_max_body_size /etc/nginx/sites-enabled/docai` (should be 52M)
- Check permissions: `ls -ld /var/lib/docai/`

**Backend won't start**
- Check logs: `sudo journalctl -u docai -n 50`
- Verify venv is set up: `ls -la /opt/docai/venv/bin/python`
- Test manual start: `cd /opt/docai && source venv/bin/activate && uvicorn docai_core.api.app:app --host 127.0.0.1 --port 8000`

**Auth not working**
- Check htpasswd file exists: `sudo ls -l /etc/nginx/.docai_htpasswd`
- Verify Nginx config has `auth_basic` lines: `grep auth_basic /etc/nginx/sites-available/docai`
- Test credentials: `curl -u alpha:alpha123 http://127.0.0.1/api/health`

## After Deployment

1. **Monitor service**
   ```bash
   sudo journalctl -u docai -f
   ```

2. **Backup regularly**
   ```bash
   # Add to crontab for daily backups
   0 2 * * * cp /var/lib/docai/docai.sqlite /opt/backups/docai.sqlite.\$(date +\%Y\%m\%d)
   ```

3. **Enable HTTPS** (recommended for production)
   - Use Let's Encrypt + Certbot
   - See full DEPLOYMENT.md for details

4. **Monitor disk space**
   ```bash
   df -h /var/lib/docai/
   ```

## Contact & Support

For deployment issues:
1. Check `sudo journalctl -u docai -f` for service errors
2. Check `sudo tail -f /var/log/nginx/error.log` for Nginx errors
3. Verify health: `curl -u alpha:alpha123 http://<ip>/api/health`
4. Check git commit: `git log --oneline -1` (should be deployment commit)

---

**Status**: ✅ Ready for public alpha deployment  
**Public Access**: Requires Basic Auth  
**Support**: Email or documentation  
**Backup**: Configure daily backups before going live
