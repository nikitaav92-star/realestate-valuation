# TASK-007: Deploy Web Viewer via Cloudflare Tunnel

**Status:** 🔵 IN PROGRESS  
**Priority:** HIGH  
**Assigned to:** Claude Agent  
**Created:** 2025-11-04  
**Sprint:** Current

---

## Problem Statement

Web viewer running on http://51.75.16.178:8000 is not accessible from outside.
Need to expose it securely via ourdocs.org domain using Cloudflare.

### Current State:
- ✅ Web viewer running on port 8000
- ✅ 1,558 listings in database
- ❌ Port 8000 blocked by firewall or ISP
- ❌ No HTTPS/SSL
- ❌ No domain access

### Desired State:
- ✅ Accessible via subdomain (e.g., realestate.ourdocs.org)
- ✅ HTTPS enabled automatically
- ✅ Secure Cloudflare Tunnel (no port forwarding needed)
- ✅ Documented deployment process

---

## Technical Approach

### Option 1: Cloudflare Tunnel (Recommended)
**Pros:**
- No firewall changes needed
- Automatic HTTPS
- Secure (no exposed ports)
- Free for personal use
- Easy setup with cloudflared daemon

**Steps:**
1. Install cloudflared on server
2. Authenticate with Cloudflare API
3. Create tunnel: `cloudflared tunnel create realestate`
4. Configure tunnel to route realestate.ourdocs.org → localhost:8000
5. Run tunnel as systemd service
6. Update DNS in Cloudflare dashboard

### Option 2: Direct Port + Cloudflare Proxy
**Pros:**
- Simpler architecture
- Lower latency

**Cons:**
- Requires firewall configuration
- Server IP exposed
- Need to manage SSL manually

**Decision:** Use Option 1 (Cloudflare Tunnel)

---

## Implementation Plan

### Phase 1: Setup Cloudflare Access
- [ ] Get Cloudflare API credentials from .env or user
- [ ] Verify domain ourdocs.org exists in Cloudflare account
- [ ] Choose subdomain (realestate.ourdocs.org or viewer.ourdocs.org)

### Phase 2: Install cloudflared
```bash
# Download and install
wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared-linux-amd64.deb

# Verify installation
cloudflared --version
```

### Phase 3: Create and Configure Tunnel
```bash
# Authenticate (opens browser or provides URL)
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create realestate

# Get tunnel ID and credentials
# Stored in ~/.cloudflared/<UUID>.json

# Create config file
cat > ~/.cloudflared/config.yml << YAML
tunnel: <UUID>
credentials-file: /home/ubuntu/.cloudflared/<UUID>.json

ingress:
  - hostname: realestate.ourdocs.org
    service: http://localhost:8000
  - service: http_status:404
YAML

# Create DNS record
cloudflared tunnel route dns realestate realestate.ourdocs.org
```

### Phase 4: Setup Systemd Service
```bash
# Install as service
sudo cloudflared service install

# Enable and start
sudo systemctl enable cloudflared
sudo systemctl start cloudflared

# Check status
sudo systemctl status cloudflared
```

### Phase 5: Verification
- [ ] Access https://realestate.ourdocs.org
- [ ] Verify SSL certificate (automatic via Cloudflare)
- [ ] Test all web viewer features
- [ ] Check logs: `journalctl -u cloudflared -f`

---

## Files to Create/Modify

### New Files:
- `~/.cloudflared/config.yml` - Tunnel configuration
- `~/.cloudflared/<UUID>.json` - Tunnel credentials (auto-generated)
- `infra/cloudflare/tunnel-setup.sh` - Deployment script
- `docs/CLOUDFLARE_DEPLOYMENT.md` - User guide

### Modified Files:
- `.env` - Add CLOUDFLARE_API_TOKEN (if needed)
- `README.md` - Update with new URL

---

## Security Considerations

1. **Tunnel Credentials:**
   - Store `<UUID>.json` securely
   - Do NOT commit to Git (add to .gitignore)
   - Backup credentials to secure location

2. **API Tokens:**
   - Use scoped tokens (Tunnel creation only)
   - Store in .env file
   - Never commit to repository

3. **Access Control:**
   - Consider adding Cloudflare Access for authentication
   - Rate limiting via Cloudflare dashboard
   - Monitor access logs

---

## Testing Checklist

- [ ] Tunnel daemon running (`systemctl status cloudflared`)
- [ ] DNS resolves: `nslookup realestate.ourdocs.org`
- [ ] HTTPS works: `curl -I https://realestate.ourdocs.org`
- [ ] Web interface loads in browser
- [ ] All filters and sorting work
- [ ] Links to CIAN.ru work
- [ ] No error logs in `journalctl -u cloudflared`

---

## Rollback Plan

If deployment fails:
1. Stop tunnel: `sudo systemctl stop cloudflared`
2. Disable service: `sudo systemctl disable cloudflared`
3. Delete DNS record in Cloudflare dashboard
4. Revert to local testing (port 8000)

---

## Success Criteria

- ✅ Web viewer accessible at https://realestate.ourdocs.org
- ✅ HTTPS with valid SSL certificate
- ✅ Cloudflared running as systemd service
- ✅ Automatic restart on server reboot
- ✅ Documentation updated
- ✅ User can view all 1,558 listings

---

## Dependencies

**Required:**
- Cloudflare account with ourdocs.org domain
- Cloudflare API token with Tunnel permissions
- Server with internet access (51.75.16.178)
- Web viewer running on port 8000

**Optional:**
- Cloudflare Access for auth (can add later)
- Custom domain SSL certificate (Cloudflare provides free)

---

## Estimated Time

- Setup: 15-20 minutes
- Testing: 5 minutes
- Documentation: 10 minutes
- **Total:** ~30-35 minutes

---

## References

- [Cloudflare Tunnel Docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
- [cloudflared GitHub](https://github.com/cloudflare/cloudflared)
- [DNS Setup Guide](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/routing-to-tunnel/dns/)

---

## Notes

- Cloudflare Tunnel is free for personal use
- No need to open firewall ports
- Automatic HTTPS renewal
- Works with any hosting provider
- Can tunnel multiple services from same server

---

## Next Steps After Completion

1. Add to monitoring (uptime checks)
2. Setup Cloudflare Analytics
3. Configure caching rules for static assets
4. Consider adding Cloudflare Workers for API routes
5. Setup Cloudflare Access for team authentication
