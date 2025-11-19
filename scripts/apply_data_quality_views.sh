#!/bin/bash
# TASK-005: Apply Data Quality Views
# Create SQL views for data quality metrics

set -euo pipefail

echo "📊 Applying data quality views..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

DB_NAME="${POSTGRES_DB:-realdb}"
DB_USER="${POSTGRES_USER:-realuser}"
DB_PASS="${POSTGRES_PASSWORD:-}"

# Check if Docker container is running
if ! docker ps | grep -q "realestate-postgres"; then
    echo "❌ PostgreSQL container is not running"
    echo "   Start it with: docker compose up -d postgres"
    exit 1
fi

# Apply views
echo "📋 Creating data quality views..."
PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f db/views_data_quality.sql

echo "✅ Data quality views created!"
echo ""
echo "📊 Available views:"
echo "   - data_quality_metrics (overall metrics)"
echo "   - data_quality_metrics_recent (last 7 days)"
echo "   - apartment_shares_detected (shares < 20m²)"
echo ""
echo "🔍 Example queries:"
echo "   SELECT * FROM data_quality_metrics;"
echo "   SELECT * FROM data_quality_metrics_recent;"
echo "   SELECT COUNT(*) FROM apartment_shares_detected;"

