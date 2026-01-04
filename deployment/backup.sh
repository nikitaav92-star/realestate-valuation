#!/bin/bash
# 💾 Backup script for database and logs

BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}💾 Creating backup${NC}"
echo "==================="
echo ""

mkdir -p $BACKUP_DIR

# Backup database
echo -e "${YELLOW}Backing up database...${NC}"
pg_dump -U realuser realdb | gzip > "$BACKUP_DIR/db_$DATE.sql.gz"
echo -e "${GREEN}✅ Database backed up${NC}"

# Backup valuation history
echo -e "${YELLOW}Backing up valuation history...${NC}"
psql -U realuser realdb -c "COPY valuation_history TO STDOUT CSV HEADER" | gzip > "$BACKUP_DIR/history_$DATE.csv.gz"
echo -e "${GREEN}✅ History backed up${NC}"

# Backup logs
if [ -d "/var/log/valuation" ]; then
    echo -e "${YELLOW}Backing up logs...${NC}"
    tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" /var/log/valuation/ 2>/dev/null
    echo -e "${GREEN}✅ Logs backed up${NC}"
fi

# Keep only last 7 backups
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "history_*.csv.gz" -mtime +7 -delete
find $BACKUP_DIR -name "logs_*.tar.gz" -mtime +7 -delete

# Show backup size
TOTAL_SIZE=$(du -sh $BACKUP_DIR | cut -f1)

echo ""
echo -e "${GREEN}✅ Backup complete!${NC}"
echo "Location: $BACKUP_DIR"
echo "Total size: $TOTAL_SIZE"
echo ""
echo "Latest backups:"
ls -lht $BACKUP_DIR | head -5
