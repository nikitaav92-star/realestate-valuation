# Operations Runbook - Real Estate Platform

**Version:** 1.0  
**Last Updated:** 2025-11-19  
**Status:** ✅ Production Ready

---

## 📋 Table of Contents

1. [Quick Reference](#quick-reference)
2. [Daily Operations](#daily-operations)
3. [Weekly Operations](#weekly-operations)
4. [Monthly Operations](#monthly-operations)
5. [Troubleshooting](#troubleshooting)
6. [Emergency Procedures](#emergency-procedures)
7. [Service Management](#service-management)
8. [Database Operations](#database-operations)
9. [Monitoring & Health Checks](#monitoring--health-checks)
10. [Backup & Recovery](#backup--recovery)

---

## 🚀 Quick Reference

### Service Status Check
```bash
# All services
docker compose ps
sudo systemctl status realestate-web

# Database
docker exec realestate-postgres-1 pg_isready -U realuser

# Web interface
curl http://localhost:8000/health

# API
curl http://localhost:8080/health
```

### Quick Restart
```bash
# Web service
sudo systemctl restart realestate-web

# All Docker services
docker compose restart

# Database only
docker compose restart postgres
```

### Logs
```bash
# Web service logs
sudo journalctl -u realestate-web -f --lines 50

# Docker logs
docker compose logs -f

# Database logs
docker compose logs postgres -f
```

---

## 📅 Daily Operations

### Morning Checklist (5 minutes)

1. **Check Service Status**
   ```bash
   docker compose ps
   sudo systemctl status realestate-web
   ```

2. **Verify Database Health**
   ```bash
   docker exec realestate-postgres-1 pg_isready -U realuser
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c "SELECT COUNT(*) FROM listings;"
   ```

3. **Check Recent Errors**
   ```bash
   sudo journalctl -u realestate-web --since "1 hour ago" | grep -i error
   docker compose logs --since 1h | grep -i error
   ```

4. **Verify Disk Space**
   ```bash
   df -h
   du -sh db/data/
   ```

5. **Check Backup Status**
   ```bash
   ls -lh /backups/ | tail -5
   ```

### End of Day Checklist (5 minutes)

1. **Review Daily Metrics**
   ```bash
   # New listings today
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listings WHERE first_seen::date = CURRENT_DATE;"
   
   # Price updates today
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listing_prices WHERE seen_at::date = CURRENT_DATE;"
   ```

2. **Check Error Rates**
   ```bash
   sudo journalctl -u realestate-web --since "24 hours ago" | grep -c error
   ```

3. **Verify Backup Completed**
   ```bash
   ls -lh /backups/ | grep $(date +%Y%m%d)
   ```

---

## 📆 Weekly Operations

### Monday Morning (15 minutes)

1. **Weekly Health Report**
   ```bash
   # Total listings
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) as total_listings FROM listings;"
   
   # Data quality
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT 
       COUNT(*) as total,
       COUNT(*) FILTER (WHERE rooms IS NOT NULL) * 100.0 / COUNT(*) as pct_rooms,
       COUNT(*) FILTER (WHERE area_total IS NOT NULL) * 100.0 / COUNT(*) as pct_area,
       COUNT(*) FILTER (WHERE address IS NOT NULL) * 100.0 / COUNT(*) as pct_address
     FROM listings;"
   ```

2. **Review Logs for Issues**
   ```bash
   sudo journalctl -u realestate-web --since "7 days ago" | grep -i "error\|warning" | tail -20
   ```

3. **Check Disk Usage Trends**
   ```bash
   du -sh db/data/
   # Compare with last week
   ```

### Friday Afternoon (30 minutes)

1. **Update Dependencies** (if needed)
   ```bash
   cd /home/ubuntu/realestate
   source venv/bin/activate
   pip list --outdated
   # Review and update carefully
   ```

2. **Review Backup Retention**
   ```bash
   ls -lh /backups/ | wc -l
   # Should have ~30 backups (30 days retention)
   ```

3. **Performance Review**
   ```bash
   # Average response time (if monitoring available)
   # Database query performance
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT schemaname, tablename, n_live_tup, n_dead_tup 
      FROM pg_stat_user_tables 
      ORDER BY n_dead_tup DESC;"
   ```

---

## 📊 Monthly Operations

### First Monday of Month (1 hour)

1. **Security Updates**
   ```bash
   sudo apt update
   sudo apt list --upgradable
   sudo apt upgrade -y
   ```

2. **Docker Updates**
   ```bash
   docker compose pull
   docker compose up -d
   ```

3. **Database Maintenance**
   ```bash
   # Vacuum and analyze
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c "VACUUM ANALYZE;"
   
   # Check table sizes
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT 
       schemaname,
       tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
     FROM pg_tables
     WHERE schemaname = 'public'
     ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;"
   ```

4. **Review and Archive Old Logs**
   ```bash
   # Archive logs older than 30 days
   sudo journalctl --since "30 days ago" --until "31 days ago" > /backups/logs/archive_$(date +%Y%m).log
   ```

5. **Capacity Planning**
   ```bash
   # Database growth rate
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT 
       DATE_TRUNC('month', first_seen) as month,
       COUNT(*) as new_listings
     FROM listings
     GROUP BY month
     ORDER BY month DESC
     LIMIT 6;"
   ```

---

## 🔧 Troubleshooting

### Service Won't Start

**Symptoms:** Service fails to start or immediately crashes

**Diagnosis:**
```bash
# Check service status
sudo systemctl status realestate-web

# Check logs
sudo journalctl -u realestate-web -n 50

# Check port availability
sudo lsof -i :8000
```

**Common Causes:**
1. Port already in use
2. Missing environment variables
3. Database connection failure
4. Python dependencies missing

**Solutions:**
```bash
# Kill process on port
sudo lsof -ti :8000 | xargs sudo kill -9

# Verify environment
cat .env | grep PG_DSN

# Test database connection
PGPASSWORD=$(grep POSTGRES_PASSWORD .env | cut -d '=' -f2) \
psql -h localhost -U realuser -d realdb -c "SELECT 1;"

# Reinstall dependencies
cd /home/ubuntu/realestate
source venv/bin/activate
pip install -r requirements.txt
```

### Database Connection Errors

**Symptoms:** "Connection refused" or "Authentication failed"

**Diagnosis:**
```bash
# Check if PostgreSQL is running
docker compose ps postgres

# Check database logs
docker compose logs postgres --tail 50

# Test connection
docker exec realestate-postgres-1 pg_isready -U realuser
```

**Solutions:**
```bash
# Restart PostgreSQL
docker compose restart postgres

# Wait for startup
sleep 10

# Verify connection
docker exec realestate-postgres-1 psql -U realuser -d realdb -c "SELECT 1;"
```

### High Memory Usage

**Symptoms:** System slow, OOM errors

**Diagnosis:**
```bash
# Check memory usage
free -h

# Check Docker memory
docker stats --no-stream

# Check process memory
ps aux --sort=-%mem | head -10
```

**Solutions:**
```bash
# Restart services to free memory
docker compose restart
sudo systemctl restart realestate-web

# If persistent, check for memory leaks
docker stats --no-stream realestate-postgres-1
```

### Disk Space Issues

**Symptoms:** "No space left on device"

**Diagnosis:**
```bash
# Check disk usage
df -h

# Check database size
docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
  "SELECT pg_size_pretty(pg_database_size('realdb'));"

# Check log sizes
du -sh /var/log/journal/
du -sh db/data/
```

**Solutions:**
```bash
# Clean old Docker images
docker system prune -a

# Vacuum database
docker exec realestate-postgres-1 psql -U realuser -d realdb -c "VACUUM FULL;"

# Clean old backups (keep last 30 days)
find /backups/ -name "*.sql" -mtime +30 -delete

# Rotate logs
sudo journalctl --vacuum-time=30d
```

---

## 🚨 Emergency Procedures

### Complete System Failure

**Scenario:** All services down, system unresponsive

**Steps:**
1. **Assess Situation**
   ```bash
   # Check system status
   uptime
   free -h
   df -h
   ```

2. **Restart Services**
   ```bash
   # Restart Docker
   sudo systemctl restart docker
   sleep 5
   
   # Start containers
   cd /home/ubuntu/realestate
   docker compose up -d
   
   # Start web service
   sudo systemctl start realestate-web
   ```

3. **Verify Recovery**
   ```bash
   docker compose ps
   sudo systemctl status realestate-web
   curl http://localhost:8000/health
   ```

### Database Corruption

**Scenario:** Database errors, data inconsistency

**Steps:**
1. **Stop Services**
   ```bash
   sudo systemctl stop realestate-web
   docker compose stop postgres
   ```

2. **Restore from Backup**
   ```bash
   # Find latest backup
   ls -lt /backups/*.sql | head -1
   
   # Restore
   LATEST_BACKUP=$(ls -t /backups/*.sql | head -1)
   cat $LATEST_BACKUP | docker exec -i realestate-postgres-1 psql -U realuser realdb
   ```

3. **Verify Data**
   ```bash
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listings;"
   ```

4. **Restart Services**
   ```bash
   docker compose start postgres
   sudo systemctl start realestate-web
   ```

### Security Incident

**Scenario:** Unauthorized access detected

**Steps:**
1. **Immediate Actions**
   ```bash
   # Block suspicious IPs
   sudo ufw deny from <suspicious_ip>
   
   # Check recent logins
   sudo last -n 20
   
   # Check for unauthorized changes
   sudo find /home/ubuntu/realestate -mtime -1 -type f
   ```

2. **Rotate Credentials**
   ```bash
   # Generate new passwords
   openssl rand -base64 32
   
   # Update .env file
   nano .env
   
   # Restart services
   docker compose restart
   sudo systemctl restart realestate-web
   ```

3. **Investigate**
   ```bash
   # Check audit logs
   sudo ausearch -m all -ts recent
   
   # Review access logs
   sudo journalctl -u realestate-web | grep -i "unauthorized\|forbidden"
   ```

---

## 🔄 Service Management

### Starting Services

```bash
# Start all Docker services
cd /home/ubuntu/realestate
docker compose up -d

# Start web service
sudo systemctl start realestate-web

# Enable auto-start
sudo systemctl enable realestate-web
```

### Stopping Services

```bash
# Stop web service
sudo systemctl stop realestate-web

# Stop Docker services
docker compose stop

# Stop specific service
docker compose stop postgres
```

### Restarting Services

```bash
# Restart web service
sudo systemctl restart realestate-web

# Restart all Docker services
docker compose restart

# Restart specific service
docker compose restart postgres
```

### Updating Services

```bash
# Pull latest images
docker compose pull

# Rebuild and restart
docker compose up -d --build

# Update web service code
cd /home/ubuntu/realestate
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart realestate-web
```

---

## 🗄️ Database Operations

### Backup

```bash
# Manual backup
docker exec realestate-postgres-1 pg_dump -U realuser realdb > \
  /backups/manual_$(date +%Y%m%d_%H%M%S).sql

# Automated backup (runs daily at 2 AM via cron)
# See: scripts/backup_db.sh
```

### Restore

```bash
# Restore from backup
BACKUP_FILE=/backups/backup_20251119.sql
cat $BACKUP_FILE | docker exec -i realestate-postgres-1 psql -U realuser realdb
```

### Maintenance

```bash
# Vacuum (reclaim space)
docker exec realestate-postgres-1 psql -U realuser -d realdb -c "VACUUM;"

# Analyze (update statistics)
docker exec realestate-postgres-1 psql -U realuser -d realdb -c "ANALYZE;"

# Full maintenance
docker exec realestate-postgres-1 psql -U realuser -d realdb -c "VACUUM ANALYZE;"
```

### Query Examples

```bash
# Count listings
docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
  "SELECT COUNT(*) FROM listings;"

# Recent listings
docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
  "SELECT id, address, rooms, price FROM listings ORDER BY first_seen DESC LIMIT 10;"

# Data quality check
docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
  "SELECT 
     COUNT(*) as total,
     COUNT(*) FILTER (WHERE rooms IS NOT NULL) as has_rooms,
     COUNT(*) FILTER (WHERE area_total IS NOT NULL) as has_area,
     COUNT(*) FILTER (WHERE address IS NOT NULL) as has_address
   FROM listings;"
```

---

## 📊 Monitoring & Health Checks

### Health Check Endpoints

```bash
# Web interface health
curl http://localhost:8000/health

# API health
curl http://localhost:8080/health

# Database health
docker exec realestate-postgres-1 pg_isready -U realuser
```

### Manual Health Check Script

```bash
#!/bin/bash
# scripts/health_check.sh

echo "=== Health Check ==="
echo ""

# Docker services
echo "Docker Services:"
docker compose ps
echo ""

# Web service
echo "Web Service:"
sudo systemctl is-active realestate-web
echo ""

# Database
echo "Database:"
docker exec realestate-postgres-1 pg_isready -U realuser
echo ""

# Disk space
echo "Disk Space:"
df -h | grep -E "Filesystem|/$"
echo ""

# Memory
echo "Memory:"
free -h
```

### Monitoring Commands

```bash
# Real-time Docker stats
docker stats

# Service logs (last 100 lines)
sudo journalctl -u realestate-web -n 100

# Database connections
docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

---

## 💾 Backup & Recovery

### Backup Procedures

**Automated Daily Backup:**
- **Schedule:** Daily at 2:00 AM
- **Location:** `/backups/`
- **Retention:** 30 days
- **Format:** SQL dump

**Manual Backup:**
```bash
BACKUP_FILE=/backups/manual_$(date +%Y%m%d_%H%M%S).sql
docker exec realestate-postgres-1 pg_dump -U realuser realdb > $BACKUP_FILE
gzip $BACKUP_FILE
```

### Recovery Procedures

**Full Database Recovery:**
```bash
# Stop services
sudo systemctl stop realestate-web
docker compose stop postgres

# Restore
BACKUP_FILE=/backups/backup_20251119.sql.gz
gunzip -c $BACKUP_FILE | docker exec -i realestate-postgres-1 psql -U realuser realdb

# Verify
docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
  "SELECT COUNT(*) FROM listings;"

# Restart services
docker compose start postgres
sudo systemctl start realestate-web
```

**Partial Recovery (specific table):**
```bash
# Extract specific table from backup
pg_restore -t listings /backups/backup.sql | \
  docker exec -i realestate-postgres-1 psql -U realuser realdb
```

---

## 📞 Support Contacts

### Escalation Path

1. **Level 1:** Check this runbook
2. **Level 2:** Review logs and diagnostics
3. **Level 3:** Contact DevOps team
4. **Level 4:** Emergency on-call

### Useful Links

- **Documentation:** `/home/ubuntu/realestate/docs/`
- **Logs:** `/var/log/realestate/`
- **Backups:** `/backups/`
- **Configuration:** `/home/ubuntu/realestate/.env`

---

## 📝 Change Log

- **2025-11-19:** Initial runbook created
- **Version 1.0:** Production-ready operations guide

---

**This runbook is a living document. Update it as procedures change.**

