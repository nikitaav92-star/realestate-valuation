#!/bin/bash
# Create Read-Only Database User for API
# TASK-PROD-020: Database read-only user

set -euo pipefail

echo "👤 Creating read-only database user for API..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default values
DB_NAME="${POSTGRES_DB:-realdb}"
DB_USER="${POSTGRES_USER:-realuser}"
DB_PASS="${POSTGRES_PASSWORD:-}"
READONLY_USER="${READONLY_DB_USER:-realestate_readonly}"
READONLY_PASS="${READONLY_DB_PASS:-$(openssl rand -base64 32)}"

echo "📋 Configuration:"
echo "   Database: $DB_NAME"
echo "   Admin User: $DB_USER"
echo "   Read-Only User: $READONLY_USER"
echo ""

# Check if Docker container is running
if ! docker ps | grep -q "realestate-postgres"; then
    echo "❌ PostgreSQL container is not running"
    echo "   Start it with: docker compose up -d postgres"
    exit 1
fi

# Create read-only user
echo "🔨 Creating read-only user..."

docker exec -i realestate-postgres-1 psql -U "$DB_USER" -d postgres <<EOF
-- Create read-only user if not exists
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = '$READONLY_USER') THEN
        CREATE USER $READONLY_USER WITH PASSWORD '$READONLY_PASS';
        RAISE NOTICE 'User $READONLY_USER created';
    ELSE
        RAISE NOTICE 'User $READONLY_USER already exists';
    END IF;
END
\$\$;

-- Grant connect privilege
GRANT CONNECT ON DATABASE $DB_NAME TO $READONLY_USER;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO $READONLY_USER;

-- Grant select on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO $READONLY_USER;

-- Grant select on all existing sequences
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO $READONLY_USER;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO $READONLY_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON SEQUENCES TO $READONLY_USER;
EOF

echo "✅ Read-only user created successfully"
echo ""

# Test the connection
echo "🧪 Testing read-only connection..."
if docker exec -i realestate-postgres-1 psql -U "$READONLY_USER" -d "$DB_NAME" -c "SELECT COUNT(*) FROM listings;" &>/dev/null; then
    echo "✅ Read-only access verified"
else
    echo "❌ Read-only access test failed"
    exit 1
fi

# Test write access (should fail)
echo "🧪 Verifying write access is blocked..."
if docker exec -i realestate-postgres-1 psql -U "$READONLY_USER" -d "$DB_NAME" -c "INSERT INTO listings (id, url, first_seen, last_seen, is_active) VALUES (999999999, 'test', NOW(), NOW(), TRUE);" &>/dev/null; then
    echo "⚠️  WARNING: Write access is NOT blocked!"
    exit 1
else
    echo "✅ Write access correctly blocked"
fi

# Save credentials to .env file
echo ""
echo "💾 Saving credentials to .env file..."
if [ -f .env ]; then
    # Remove old entries if they exist
    sed -i '/^READONLY_DB_USER=/d' .env
    sed -i '/^READONLY_DB_PASS=/d' .env
    
    # Add new entries
    echo "" >> .env
    echo "# Read-only database user for API" >> .env
    echo "READONLY_DB_USER=$READONLY_USER" >> .env
    echo "READONLY_DB_PASS=$READONLY_PASS" >> .env
    
    echo "✅ Credentials saved to .env"
else
    echo "⚠️  .env file not found, creating..."
    cat > .env <<ENV
# Read-only database user for API
READONLY_DB_USER=$READONLY_USER
READONLY_DB_PASS=$READONLY_PASS
ENV
fi

echo ""
echo "✅ Read-only user setup complete!"
echo ""
echo "📋 Summary:"
echo "   Username: $READONLY_USER"
echo "   Password: $READONLY_PASS"
echo "   Database: $DB_NAME"
echo ""
echo "📝 Connection string:"
echo "   postgresql://$READONLY_USER:$READONLY_PASS@localhost:5432/$DB_NAME"
echo ""
echo "⚠️  IMPORTANT: Save the password securely!"
echo "   It has been saved to .env file"
echo ""
echo "🔍 To test connection:"
echo "   PGPASSWORD='$READONLY_PASS' psql -h localhost -U $READONLY_USER -d $DB_NAME"
echo ""
echo "📝 To use in API:"
echo "   Update api/main.py to use READONLY_DB_USER and READONLY_DB_PASS from environment"

