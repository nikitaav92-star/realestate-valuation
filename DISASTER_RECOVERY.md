# Disaster Recovery Plan - Real Estate Platform

**Version:** 1.0  
**Last Updated:** 2025-11-19  
**Status:** ✅ Production Ready

---

## 📋 Executive Summary

This document outlines the disaster recovery procedures for the Real Estate Data Platform. It defines Recovery Time Objectives (RTO) and Recovery Point Objectives (RPO), identifies critical systems, and provides step-by-step recovery procedures.

---

## 🎯 Recovery Objectives

### Recovery Time Objectives (RTO)

| Component | RTO | Priority |
|-----------|-----|----------|
| Database | 4 hours | Critical |
| Web Interface | 2 hours | High |
| API Service | 2 hours | High |
| ETL Pipeline | 24 hours | Medium |
| Monitoring | 48 hours | Low |

### Recovery Point Objectives (RPO)

| Component | RPO | Backup Frequency |
|-----------|-----|-----------------|
| Database | 24 hours | Daily at 2 AM |
| Configuration | 1 week | Weekly |
| Application Code | 1 day | Git repository |

---

## 🔴 Critical Systems

### Tier 1: Critical (Must restore immediately)

1. **PostgreSQL Database**
   - Contains all listing data
   - Price history
   - No acceptable data loss

2. **Web Interface**
   - User-facing application
   - Primary access point

### Tier 2: High Priority (Restore within 4 hours)

3. **API Service**
   - External integrations
   - Data access for applications

4. **Backup System**
   - Ensures data recovery capability

### Tier 3: Medium Priority (Restore within 24 hours)

5. **ETL Pipeline**
   - Data collection
   - Can be paused temporarily

6. **Monitoring**
   - Observability
   - Can use manual checks temporarily

---

## 📊 Risk Assessment

### High Risk Scenarios

1. **Database Corruption**
   - **Probability:** Low
   - **Impact:** Critical
   - **Mitigation:** Daily backups, transaction logs

2. **Hardware Failure**
   - **Probability:** Medium
   - **Impact:** Critical
   - **Mitigation:** Cloud hosting, backups

3. **Data Center Outage**
   - **Probability:** Low
   - **Impact:** Critical
   - **Mitigation:** Off-site backups, cloud migration plan

4. **Security Breach**
   - **Probability:** Low
   - **Impact:** High
   - **Mitigation:** Security hardening, monitoring

### Medium Risk Scenarios

5. **Application Failure**
   - **Probability:** Medium
   - **Impact:** High
   - **Mitigation:** Health checks, auto-restart

6. **Network Outage**
   - **Probability:** Low
   - **Impact:** High
   - **Mitigation:** Multiple network paths

---

## 🚨 Disaster Scenarios & Procedures

### Scenario 1: Complete Server Failure

**Symptoms:**
- Server unresponsive
- All services down
- No SSH access

**Recovery Steps:**

1. **Assess Situation** (5 minutes)
   ```bash
   # Try to access server
   ping <server_ip>
   ssh <server_ip>
   ```

2. **Contact Hosting Provider** (15 minutes)
   - Report outage
   - Request server status
   - Request recovery options

3. **Prepare Recovery Environment** (30 minutes)
   ```bash
   # On backup server or new instance
   # Install dependencies
   sudo apt update
   sudo apt install -y docker.io docker-compose python3-pip python3-venv git
   
   # Clone repository
   git clone <repository_url> realestate
   cd realestate
   ```

4. **Restore Database** (1 hour)
   ```bash
   # Download latest backup
   scp user@backup-server:/backups/latest.sql.gz .
   gunzip latest.sql.gz
   
   # Start PostgreSQL
   docker compose up -d postgres
   sleep 15
   
   # Restore database
   cat latest.sql | docker exec -i realestate-postgres-1 psql -U realuser realdb
   ```

5. **Restore Application** (30 minutes)
   ```bash
   # Setup Python environment
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   
   # Configure environment
   cp .env.example .env
   nano .env  # Update with correct values
   
   # Start services
   docker compose up -d
   sudo systemctl start realestate-web
   ```

6. **Verify Recovery** (15 minutes)
   ```bash
   # Check services
   docker compose ps
   sudo systemctl status realestate-web
   
   # Test endpoints
   curl http://localhost:8000/health
   curl http://localhost:8080/health
   
   # Verify data
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listings;"
   ```

**Total Recovery Time:** ~2.5 hours  
**Data Loss:** Up to 24 hours (last backup)

---

### Scenario 2: Database Corruption

**Symptoms:**
- Database errors
- Inconsistent data
- Application failures

**Recovery Steps:**

1. **Stop Services** (5 minutes)
   ```bash
   sudo systemctl stop realestate-web
   docker compose stop postgres
   ```

2. **Assess Damage** (15 minutes)
   ```bash
   # Try to connect
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c "SELECT 1;"
   
   # Check for corruption
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT * FROM pg_stat_database WHERE datname = 'realdb';"
   ```

3. **Attempt Repair** (30 minutes)
   ```bash
   # Try VACUUM FULL
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c "VACUUM FULL;"
   
   # Check if successful
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c "SELECT 1;"
   ```

4. **If Repair Fails, Restore from Backup** (1 hour)
   ```bash
   # Find latest backup
   ls -lt /backups/*.sql | head -1
   
   # Drop and recreate database
   docker exec realestate-postgres-1 psql -U realuser -d postgres -c \
     "DROP DATABASE realdb;"
   docker exec realestate-postgres-1 psql -U realuser -d postgres -c \
     "CREATE DATABASE realdb;"
   
   # Restore
   LATEST_BACKUP=$(ls -t /backups/*.sql | head -1)
   cat $LATEST_BACKUP | docker exec -i realestate-postgres-1 psql -U realuser realdb
   
   # Apply schema if needed
   docker exec -i realestate-postgres-1 psql -U realuser -d realdb < db/schema.sql
   ```

5. **Verify Data Integrity** (15 minutes)
   ```bash
   # Check record counts
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listings;"
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listing_prices;"
   
   # Check data quality
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE rooms IS NOT NULL) as has_rooms,
        COUNT(*) FILTER (WHERE address IS NOT NULL) as has_address
      FROM listings;"
   ```

6. **Restart Services** (5 minutes)
   ```bash
   docker compose start postgres
   sleep 10
   sudo systemctl start realestate-web
   ```

**Total Recovery Time:** ~2 hours  
**Data Loss:** Up to 24 hours (last backup)

---

### Scenario 3: Security Breach

**Symptoms:**
- Unauthorized access detected
- Suspicious activity in logs
- Data tampering

**Recovery Steps:**

1. **Immediate Isolation** (5 minutes)
   ```bash
   # Block suspicious IPs
   sudo ufw deny from <suspicious_ip>
   
   # Stop services
   sudo systemctl stop realestate-web
   docker compose stop
   ```

2. **Assess Damage** (30 minutes)
   ```bash
   # Check for unauthorized changes
   sudo find /home/ubuntu/realestate -mtime -1 -type f
   
   # Review access logs
   sudo last -n 50
   sudo journalctl -u realestate-web --since "24 hours ago" | grep -i "unauthorized"
   
   # Check database for tampering
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listings WHERE last_seen > NOW() - INTERVAL '1 hour';"
   ```

3. **Rotate All Credentials** (30 minutes)
   ```bash
   # Generate new passwords
   openssl rand -base64 32  # For PostgreSQL
   openssl rand -base64 32  # For API keys
   
   # Update .env file
   nano .env
   
   # Update database password
   docker exec realestate-postgres-1 psql -U realuser -d postgres -c \
     "ALTER USER realuser WITH PASSWORD 'new_password';"
   ```

4. **Restore from Clean Backup** (1 hour)
   ```bash
   # Find backup before breach
   # Restore database
   BACKUP_BEFORE_BREACH=/backups/backup_20251118.sql
   cat $BACKUP_BEFORE_BREACH | docker exec -i realestate-postgres-1 psql -U realuser realdb
   ```

5. **Apply Security Patches** (30 minutes)
   ```bash
   # Update system
   sudo apt update && sudo apt upgrade -y
   
   # Update Docker images
   docker compose pull
   
   # Review firewall rules
   sudo ufw status verbose
   ```

6. **Restart Services** (15 minutes)
   ```bash
   docker compose up -d
   sudo systemctl start realestate-web
   
   # Verify security
   sudo ufw status
   sudo fail2ban-client status  # If installed
   ```

7. **Monitor Closely** (Ongoing)
   ```bash
   # Watch logs
   sudo journalctl -u realestate-web -f
   docker compose logs -f
   ```

**Total Recovery Time:** ~3 hours  
**Data Loss:** Up to breach detection time

---

### Scenario 4: Data Loss

**Symptoms:**
- Missing records
- Incomplete data
- Application errors

**Recovery Steps:**

1. **Identify Missing Data** (30 minutes)
   ```bash
   # Compare current vs expected
   docker exec realestate-postgres-1 psql -U realuser -d realdb -c \
     "SELECT COUNT(*) FROM listings;"
   
   # Check last backup count
   # Review application logs for errors
   ```

2. **Restore from Backup** (1 hour)
   ```bash
   # Find appropriate backup
   LATEST_BACKUP=$(ls -t /backups/*.sql | head -1)
   
   # Restore
   cat $LATEST_BACKUP | docker exec -i realestate-postgres-1 psql -U realuser realdb
   ```

3. **Re-run ETL if Needed** (Variable)
   ```bash
   # If data collection needed
   cd /home/ubuntu/realestate
   source venv/bin/activate
   python -m etl.collector_cian.cli to-db --pages 10
   ```

**Total Recovery Time:** ~2 hours  
**Data Loss:** Up to 24 hours (last backup)

---

## 🔄 Backup Strategy

### Backup Types

1. **Full Database Backup**
   - **Frequency:** Daily at 2:00 AM
   - **Retention:** 30 days
   - **Location:** `/backups/`
   - **Format:** SQL dump, compressed

2. **Configuration Backup**
   - **Frequency:** Weekly
   - **Retention:** 90 days
   - **Location:** `/backups/config/`
   - **Contents:** `.env`, `docker-compose.yml`, systemd files

3. **Code Backup**
   - **Frequency:** Continuous (Git)
   - **Retention:** Unlimited
   - **Location:** Git repository

### Backup Verification

**Daily Verification:**
```bash
# Check backup exists
ls -lh /backups/ | grep $(date +%Y%m%d)

# Verify backup integrity
gunzip -t /backups/backup_$(date +%Y%m%d).sql.gz

# Test restore (monthly)
# Restore to test database and verify
```

---

## 🏗️ Recovery Infrastructure

### Primary Site

- **Location:** Current production server
- **Components:** All services
- **Status:** Active

### Backup Site (Future)

- **Location:** TBD (Cloud or secondary server)
- **Components:** Database backups, configuration
- **Status:** Planned

### Backup Storage

- **Location:** `/backups/` on primary server
- **Off-site:** Manual copies to external storage
- **Cloud:** Future implementation

---

## 📋 Recovery Checklist

### Pre-Recovery

- [ ] Assess situation and identify disaster type
- [ ] Notify stakeholders
- [ ] Document symptoms and timeline
- [ ] Secure current state (if possible)

### During Recovery

- [ ] Stop affected services
- [ ] Locate appropriate backup
- [ ] Verify backup integrity
- [ ] Restore database
- [ ] Restore application
- [ ] Verify data integrity
- [ ] Test functionality
- [ ] Restart services

### Post-Recovery

- [ ] Verify all services running
- [ ] Monitor for 24 hours
- [ ] Document recovery process
- [ ] Update runbook if needed
- [ ] Conduct post-mortem
- [ ] Implement preventive measures

---

## 🧪 Testing & Drills

### Quarterly Recovery Drill

**Schedule:** Every 3 months

**Procedure:**
1. Simulate disaster scenario
2. Execute recovery procedure
3. Measure recovery time
4. Document issues
5. Update procedures

### Annual Full Test

**Schedule:** Once per year

**Procedure:**
1. Full system recovery test
2. Test all disaster scenarios
3. Verify backup integrity
4. Update documentation
5. Train team

---

## 📞 Emergency Contacts

### Internal Contacts

- **DevOps Lead:** [Contact Info]
- **Database Admin:** [Contact Info]
- **On-Call Engineer:** [Contact Info]

### External Contacts

- **Hosting Provider:** [Contact Info]
- **Backup Provider:** [Contact Info]
- **Security Team:** [Contact Info]

---

## 📝 Recovery Log Template

```
Date: YYYY-MM-DD
Time: HH:MM
Disaster Type: [Type]
Detected By: [Name]
Recovery Started: HH:MM
Recovery Completed: HH:MM
Recovery Time: X hours Y minutes
Data Loss: [Amount]
Services Affected: [List]
Root Cause: [Description]
Actions Taken: [List]
Lessons Learned: [Notes]
```

---

## 🔄 Continuous Improvement

### Review Schedule

- **Monthly:** Review backup success rate
- **Quarterly:** Review recovery procedures
- **Annually:** Full disaster recovery test

### Metrics to Track

- Backup success rate (target: 100%)
- Recovery time (target: < RTO)
- Data loss (target: < RPO)
- Test completion rate

---

## 📚 Related Documents

- `RUNBOOK.md` - Daily operations guide
- `PRODUCTION_REQUIREMENTS.md` - Deployment guide
- `PRODUCTION_QUICKSTART.md` - Quick start guide
- `.speckit/specifications/production-deployment.md` - Full specification

---

## 📝 Change Log

- **2025-11-19:** Initial disaster recovery plan created
- **Version 1.0:** Production-ready recovery procedures

---

**This plan is a living document. Review and update regularly.**

