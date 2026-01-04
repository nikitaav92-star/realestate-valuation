"""Flask web application for CIAN data browser."""
import logging
import os
from pathlib import Path

from flask import Flask, render_template
from dotenv import load_dotenv

# Load environment
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

LOGGER = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Register blueprints
from routes.listings import bp as listings_bp
from routes.encumbrances import bp as encumbrances_bp
from routes.local_valuation import bp as local_valuation_bp
from routes.auctions import bp as auctions_bp

app.register_blueprint(listings_bp)
app.register_blueprint(encumbrances_bp)
app.register_blueprint(local_valuation_bp)
app.register_blueprint(auctions_bp)


@app.route('/')
def index():
    """Home page with links to all sections."""
    return render_template('home.html')


@app.route('/health')
def health():
    """Health check endpoint."""
    return {'status': 'ok'}, 200


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='CIAN Web Interface')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind')
    parser.add_argument('--port', type=int, default=5003, help='Port to bind')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    
    args = parser.parse_args()
    
    LOGGER.info(f"Starting CIAN Web Interface on {args.host}:{args.port}")
    
    app.run(
        host=args.host,
        port=args.port,
        debug=args.debug,
    )

