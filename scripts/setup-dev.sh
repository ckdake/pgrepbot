#!/bin/bash

set -e

echo "🚀 Setting up PostgreSQL Replication Manager for local development..."

# Check if Python 3.11+ is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    echo "Please install Python 3.11+ and try again."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "📍 Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📚 Installing Python dependencies..."
pip install -r requirements.txt

# Create .env file for local development
if [ ! -f ".env" ]; then
    echo "⚙️  Creating .env file for local development..."
    cat > .env << EOF
# Local development environment variables
AWS_ENDPOINT_URL=http://localhost:4566
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
AWS_DEFAULT_REGION=us-east-1
REDIS_URL=redis://localhost:6379
AUTH_KEY=dev-auth-key-12345
POSTGRES_PRIMARY_HOST=localhost
POSTGRES_REPLICA_HOST=localhost

# Development mode
ENVIRONMENT=development
DEBUG=true
EOF
fi

echo ""
echo "✅ Local development environment setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Start services: make dev-services"
echo "2. Activate venv:   source venv/bin/activate"
echo "3. Run app:         make dev-run"
echo "4. Run tests:       make dev-test"
echo "5. Run linter:      make dev-lint"
echo ""
echo "🌐 The application will be available at:"
echo "   http://localhost:8000 - Main application"
echo "   http://localhost:8000/docs - API documentation"
echo ""