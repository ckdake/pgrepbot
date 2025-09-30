.PHONY: help setup dev-services dev-services-stop run test lint lint-fix build clean status

# Default target
help:
	@echo "PostgreSQL Replication Manager - Development Commands"
	@echo ""
	@echo "� Quikck Start:"
	@echo "  make setup       - Set up local development environment (first time only)"
	@echo "  make dev-services - Start supporting services (LocalStack, Redis, PostgreSQL)"
	@echo "  make run         - Run the application locally"
	@echo "  make test        - Run the test suite with coverage"
	@echo "  make lint        - Run comprehensive linting (Python, Shell, Docker, Markdown)"
	@echo ""
	@echo "📦 Production:"
	@echo "  make build       - Build production Docker image"
	@echo "  make clean       - Clean up Docker resources"
	@echo ""
	@echo "🔧 Development workflow:"
	@echo "  1. make setup           (first time setup)"
	@echo "  2. source venv/bin/activate"
	@echo "  3. make dev-services    (start services)"
	@echo "  4. make run             (start app - in another terminal)"
	@echo "  5. make test            (run tests with coverage)"
	@echo "  6. make lint            (check code quality)"
	@echo ""
	@echo "After setup, the application will be available at:"
	@echo "  http://localhost:8000 - Main application"
	@echo "  http://localhost:8000/docs - API documentation"
	@echo "  http://localhost:4566 - LocalStack dashboard"



# Set up local development environment
setup:
	@echo "🔧 Setting up local development environment..."
	@if [ ! -d "venv" ]; then \
		echo "📦 Creating virtual environment..."; \
		python3 -m venv venv; \
	fi
	@echo "📥 Installing dependencies from pyproject.toml..."
	@./venv/bin/pip install --upgrade pip
	@./venv/bin/pip install -e ".[dev,lint]"
	@echo ""
	@echo "✅ Setup complete!"
	@echo ""
	@echo "💡 Next steps:"
	@echo "  1. source venv/bin/activate"

	@echo "  3. make dev-services"
	@echo "  4. make run"

# Start supporting services (LocalStack, Redis, PostgreSQL)
dev-services:
	@echo "🐳 Starting development services..."
	@docker-compose -f docker-compose.services.yml up -d
	@echo ""
	@echo "✅ Services started successfully!"
	@echo ""
	@echo "🔧 Services available:"
	@echo "  LocalStack: http://localhost:4566"
	@echo "  Redis: localhost:6379"
	@echo "  PostgreSQL Primary: localhost:5432"
	@echo "  PostgreSQL Replica: localhost:5433"

# Stop development services
dev-services-stop:
	@echo "🛑 Stopping development services..."
	@docker-compose -f docker-compose.services.yml down

# Run the application locally
run:
	@if [ ! -d "venv" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "❌ Virtual environment not activated."; \
		echo "💡 Run: source venv/bin/activate"; \
		exit 1; \
	fi
	@echo "🚀 Starting PostgreSQL Replication Manager..."
	@echo ""
	@echo "🔧 AWS Integration Status:"
	@echo "  LocalStack (Secrets Manager): http://localhost:4566"
	@echo "  Redis: localhost:6379"
	@echo "  PostgreSQL Primary: localhost:5432"
	@echo "  PostgreSQL Replica: localhost:5433"
	@echo ""
	@echo "🧪 Test AWS integrations at: http://localhost:8000/api/aws/test"
	@echo ""
	@export AWS_ENDPOINT_URL=http://localhost:4566 && \
	export AWS_ACCESS_KEY_ID=test && \
	export AWS_SECRET_ACCESS_KEY=test && \
	export AWS_DEFAULT_REGION=us-east-1 && \
	export REDIS_HOST=localhost && \
	export REDIS_PORT=6379 && \
	export REDIS_URL=redis://localhost:6379 && \
	export AUTH_KEY=dev-auth-key-12345 && \
	python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run tests locally
test:
	@if [ ! -d "venv" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "❌ Virtual environment not activated."; \
		echo "💡 Run: source venv/bin/activate"; \
		exit 1; \
	fi
	@echo "🧪 Running test suite with coverage..."
	@export AWS_ENDPOINT_URL=http://localhost:4566 && \
	export AWS_ACCESS_KEY_ID=test && \
	export AWS_SECRET_ACCESS_KEY=test && \
	export AWS_DEFAULT_REGION=us-east-1 && \
	export REDIS_HOST=localhost && \
	export REDIS_PORT=6379 && \
	export REDIS_URL=redis://localhost:6379 && \
	python -m pytest tests/ -v --tb=short --cov=app --cov-report=term-missing --cov-report=html
	@echo ""
	@echo "📊 Coverage report generated in htmlcov/index.html"



# Run linter locally
lint:
	@if [ ! -d "venv" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "❌ Virtual environment not activated."; \
		echo "💡 Run: source venv/bin/activate"; \
		exit 1; \
	fi
	@echo "🔍 Running Python linting with ruff..."
	@python -m ruff check app/ tests/
	@echo "🎨 Running Python formatter check..."
	@python -m ruff format --check app/ tests/
	@echo "🐚 Running shell script linting..."
	@find . -name "*.sh" -type f -not -path "./venv/*" -exec shellcheck {} + || echo "No shell scripts found"
	@echo "🐳 Running Dockerfile linting..."
	@if command -v hadolint >/dev/null 2>&1; then \
		find . -name "Dockerfile*" -type f -not -path "./venv/*" -exec hadolint {} +; \
	else \
		echo "hadolint not found - install via: brew install hadolint (or see https://github.com/hadolint/hadolint)"; \
	fi
	@echo "📝 Running Markdown linting..."
	@find . -name "*.md" -type f -not -path "./venv/*" -not -path "./.pytest_cache/*" -not -path "./.ruff_cache/*" -not -path "./htmlcov/*" -exec pymarkdown scan {} + || echo "No Markdown files found"

# Fix linting issues locally
lint-fix:
	@if [ ! -d "venv" ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "❌ Virtual environment not activated."; \
		echo "💡 Run: source venv/bin/activate"; \
		exit 1; \
	fi
	@echo "🔧 Fixing Python linting issues..."
	@python -m ruff check --fix app/ tests/
	@python -m ruff format app/ tests/
	@echo "📝 Fixing Markdown formatting..."
	@find . -name "*.md" -type f -not -path "./venv/*" -not -path "./.pytest_cache/*" -not -path "./.ruff_cache/*" -not -path "./htmlcov/*" -exec pymarkdown fix {} + || echo "No Markdown files found"

# Build production Docker image (no dev tools)
build:
	@echo "📦 Building production Docker image..."
	@docker build -t postgres-replication-manager:latest .

# Clean up Docker resources
clean:
	@echo "🧹 Cleaning up Docker resources..."
	@docker-compose -f docker-compose.services.yml down -v --remove-orphans
	@docker system prune -f

# Show service status
status:
	@echo "📊 Service Status:"
	@docker-compose -f docker-compose.services.yml ps