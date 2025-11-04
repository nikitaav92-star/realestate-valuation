#!/bin/bash
# Cloudflare Tunnel Setup Script
set -e

echo "=== Cloudflare Tunnel Setup ==="
echo

# Step 1: Authenticate
echo "Step 1: Authenticating with Cloudflare..."
echo "This will open a browser window. Please login and authorize."
echo
cloudflared tunnel login

# Step 2: Create tunnel
echo
echo "Step 2: Creating tunnel..."
cloudflared tunnel create realestate

# Get tunnel ID
TUNNEL_ID=$(cloudflared tunnel list | grep realestate | awk "{print \$1}")
echo "Tunnel ID: $TUNNEL_ID"

# Step 3: Create config
echo
echo "Step 3: Creating configuration..."
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml << YAML
tunnel: $TUNNEL_ID
credentials-file: /home/ubuntu/.cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: realestate.ourdocs.org
    service: http://localhost:8000
  - service: http_status:404
YAML

echo "Config created at ~/.cloudflared/config.yml"

# Step 4: Route DNS
echo
echo "Step 4: Creating DNS record..."
cloudflared tunnel route dns realestate realestate.ourdocs.org

# Step 5: Install as service
echo
echo "Step 5: Installing systemd service..."
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Step 6: Check status
echo
echo "Step 6: Checking status..."
sudo systemctl status cloudflared --no-pager

echo
echo "=== Setup Complete! ==="
echo
echo "Your web viewer is now accessible at:"
echo "https://realestate.ourdocs.org"
echo
echo "To check logs: sudo journalctl -u cloudflared -f"
echo "To restart: sudo systemctl restart cloudflared"
echo
