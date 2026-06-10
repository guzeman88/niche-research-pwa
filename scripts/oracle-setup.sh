#!/bin/bash
# Oracle Cloud Always Free — Niche Scanner Setup
# Run this on the VM after creation: bash oracle-setup.sh

set -e

echo "=== Niche Research Pipeline — Oracle Cloud Setup ==="

# 1. System updates
echo "[1/6] Updating system..."
sudo apt-get update -qq && sudo apt-get upgrade -y -qq
sudo apt-get install -y -qq python3-pip python3-venv git nginx curl htop unzip

# 2. Clone repo
echo "[2/6] Cloning repo..."
cd /opt
sudo git clone https://github.com/guzeman88/niche-research-pwa.git
sudo chown -R $USER:$USER /opt/niche-research-pwa
cd /opt/niche-research-pwa/backend

# 3. Install Python deps
echo "[3/6] Installing Python dependencies..."
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Copy .env (you'll need to set API keys)
echo "[4/6] Setting up environment..."
cp ../.env.example ../.env
# Uncomment and set keys as needed:
# GEMINI_API_KEY=your_key
# REDDIT_CLIENT_ID=your_id
# etc.

# 5. Systemd service for the backend
echo "[5/6] Creating systemd service..."
sudo tee /etc/systemd/system/niche-api.service > /dev/null << 'SERVICE'
[Unit]
Description=Niche Research API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/niche-research-pwa/backend
Environment="PATH=/opt/niche-research-pwa/backend/venv/bin"
Environment="BACKEND_DIR=/opt/niche-research-pwa/backend"
ExecStart=/opt/niche-research-pwa/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable niche-api
sudo systemctl start niche-api

# 6. Nginx reverse proxy
echo "[6/6] Configuring nginx..."
sudo tee /etc/nginx/sites-available/niche-api > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
        proxy_buffering off;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/niche-api /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

# Allow HTTP through Oracle firewall
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || true

# Verify
echo ""
echo "=== Setup Complete ==="
sleep 3
curl -s http://localhost:8000/api/health || echo "Waiting for API to start..."
echo ""
echo "Public IP: $(curl -s ifconfig.me)"
echo ""
echo "Test: curl http://$(curl -s ifconfig.me)/api/health"
echo ""
echo "To start the scheduler:"
echo "  cd /opt/niche-research-pwa/backend"
echo "  source venv/bin/activate"
echo "  python -c \"from services.scheduler_service import start_scheduler; start_scheduler('continuous')\""
