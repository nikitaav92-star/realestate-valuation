# Systemd Auto-scraping Setup

## Status
✅ Installed and active
⏰ Next run: Daily at 3:00 AM UTC

## Files
- `/etc/systemd/system/cian-scraper.service` - Service definition  
- `/etc/systemd/system/cian-scraper.timer` - Daily trigger

## Quick Commands

### Check status
    sudo systemctl status cian-scraper.timer

### Manual run
    sudo systemctl start cian-scraper.service

### View logs
    tail -f ~/realestate/logs/cian-scraper.log

### Disable
    sudo systemctl stop cian-scraper.timer
    sudo systemctl disable cian-scraper.timer
