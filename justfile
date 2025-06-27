# Install dependencies
install:
    uv sync

# Run tests
test:
    uv run pytest

# Format code
format:
    uv run ruff format custom_components/

# Lint code
lint:
    uv run ruff check custom_components/
    uv run mypy custom_components/

# Fix linting issues
fix:
    uv run ruff check --fix custom_components/

# Type check
typecheck:
    uv run mypy custom_components/

# Build package
build:
    uv build

# Clean build artifacts
clean:
    rm -rf dist/
    rm -rf .pytest_cache/
    rm -rf __pycache__/
    rm -rf .mypy_cache/
    rm -rf .ruff_cache/
    find . -name "*.pyc" -delete
    find . -type d -name "__pycache__" -exec rm -rf {} +

# Run all checks
check: lint typecheck

# Fix and format everything
fix-all: fix format

# Run pre-commit on all files
pre-commit:
    uv run pre-commit run --all-files

# Show project info
info:
    uv tree