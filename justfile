# Default recipe
default:
    @just --list

# Run all linters
lint:
    ruff check custom_components/
    pylint custom_components/
    mypy custom_components/

# Run linters with auto-fix
fix:
    ruff check --fix custom_components/
    black custom_components/

# Format code
format:
    black custom_components/
    ruff check --select I --fix custom_components/  # Sort imports

# Type check
check:
    mypy custom_components/

# Run ruff only (fast feedback)
ruff:
    ruff check custom_components/

# Run pylint only (comprehensive)
pylint:
    pylint custom_components/

# Check but don't fix
check-all: lint check

# Fix and format everything
fix-all: fix format

# Run pre-commit on all files
pre-commit:
    pre-commit run --all-files

# Clean up cache files
clean:
    find . -type d -name "__pycache__" -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    find . -type d -name ".mypy_cache" -exec rm -rf {} +
    find . -type d -name ".pytest_cache" -exec rm -rf {} +
    find . -type d -name ".ruff_cache" -exec rm -rf {} +