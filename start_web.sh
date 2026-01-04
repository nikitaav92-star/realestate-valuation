#!/bin/bash
# Start unified web application with all features

cd /home/ubuntu/realestate
source venv/bin/activate

echo "🚀 Starting Real Estate Web Application..."
echo "📊 Main page: http://localhost:5000/"
echo "📋 Listings browser: http://localhost:5000/listings"
echo "⚠️  Encumbrances management: http://localhost:5000/encumbrances"
echo ""

cd web
python3 app.py --host 0.0.0.0 --port 5000

