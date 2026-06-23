# Quick Start with UV

**5-minute guide to get started with UV package manager**

---

## 1. Install UV (30 seconds)

### Windows
```powershell
winget install --id=astral-sh.uv -e
```

### Linux / macOS
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Verify
```bash
uv --version
# Should show: uv 0.5.16 or newer
```

---

## 2. Setup Project (10 seconds)

```bash
# Create virtual environment
uv venv --python 3.10

# Activate
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\Activate.ps1       # Windows PowerShell
```

---

## 3. Install Dependencies (5-10 seconds!)

```bash
# Install everything (recommended for development)
uv sync --all-extras

# Or just production dependencies
uv sync
```

**Expected time: 5-10 seconds** ⚡ (vs 2-3 minutes with pip!)

---

## 4. Run Application

```bash
# Option 1: Use uv run (no activation needed)
uv run python ui/gradio_app.py

# Option 2: Activate venv and run
source .venv/bin/activate
python ui/gradio_app.py
```

Open http://localhost:7860 in your browser!

---

## Common Commands

### Managing Dependencies

```bash
# Add new package
uv add numpy

# Add dev dependency
uv add --dev pytest

# Remove package
uv remove numpy

# Update all packages
uv lock --upgrade

# Update specific package
uv lock --upgrade-package gradio
```

### Running Commands

```bash
# Run Python script
uv run python script.py

# Run tests
uv run pytest

# Run formatter
uv run black .

# Run linter
uv run ruff check .
```

### Environment Management

```bash
# Create new venv
uv venv

# Create with specific Python version
uv venv --python 3.11

# Delete venv
rm -rf .venv  # Linux/macOS
rmdir /s /q .venv  # Windows
```

### Show Information

```bash
# List installed packages
uv pip list

# Show package info
uv pip show gradio

# Show dependency tree
uv pip tree
```

---

## Docker Usage

### Quick Start

```bash
# Create .env file
cp .env.example .env
# Edit .env with your API keys

# Build and start all services
docker-compose up -d --build

# View logs
docker-compose logs -f app
```

### Service Management

```bash
# Start all services
docker-compose up -d

# Start specific services
docker-compose up -d app qwen-image-edit

# Stop all services
docker-compose down

# Restart service
docker-compose restart app

# View logs
docker-compose logs -f app
```

### Rebuild After Changes

```bash
# Rebuild specific service
docker-compose build app

# Rebuild with no cache
docker-compose build --no-cache app

# Rebuild and restart
docker-compose up -d --build app
```

---

## Troubleshooting

### UV not found after installation

**Linux/macOS:**
```bash
source ~/.bashrc  # or ~/.zshrc
# OR restart terminal
```

**Windows:**
- Restart PowerShell/Terminal

### Dependencies not installing

```bash
# Clean and retry
rm uv.lock
uv lock
uv sync --all-extras
```

### Docker build fails

```bash
# Generate lock file if missing
uv lock

# Force rebuild
docker-compose build --no-cache app
```

### Port already in use

```bash
# Find process using port 7860
lsof -i :7860  # Linux/macOS
netstat -ano | findstr :7860  # Windows

# Change port in docker-compose.yml
ports:
  - "7861:7860"  # Use 7861 instead
```

---

## Performance Comparison

| Task | pip | UV | Speedup |
|------|-----|-----|---------|
| Create venv | 8s | 0.4s | **20x** ⚡ |
| Install deps | 2-3 min | 5-10s | **20-30x** ⚡ |
| Docker build | 5-7 min | 30-60s | **5-10x** ⚡ |

---

## Next Steps

1. ✅ **Read full guide**: [UV_MIGRATION_GUIDE.md](UV_MIGRATION_GUIDE.md)
2. ✅ **Docker setup**: [DOCKER.md](DOCKER.md)
3. ✅ **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md)
4. ✅ **Changelog**: [CHANGELOG_UV_DOCKER.md](CHANGELOG_UV_DOCKER.md)

---

## Support

- **UV Docs**: https://docs.astral.sh/uv/
- **GitHub Issues**: https://github.com/yourusername/3d-agent-mcp/issues
- **Discord**: Your community link here

---

**That's it! You're ready to develop with 10-100x faster dependency management!** 🚀
