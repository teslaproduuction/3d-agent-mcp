# Quick Start Guide

Get the 3D Agent Generation System up and running in 5 minutes!

## Prerequisites

You'll need:
1. Python 3.10 or higher
2. API keys from:
   - **Tripo3D** (required): https://platform.tripo3d.ai
   - **OpenAI** (required): https://platform.openai.com

## Installation Steps

### 1. Setup Virtual Environment

```bash
# Create and activate virtual environment
python -m venv .venv

# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure API Keys

**Option A: Using .env file (recommended)**

```bash
cp .env.example .env
nano .env  # Or use any text editor
```

Add your API keys:
```
TRIPO_API_KEY=your_tripo_key_here
OPENAI_API_KEY=your_openai_key_here
```

**Option B: Edit config.yaml directly**

Edit `config.yaml` and add your keys:
```yaml
api_keys:
  tripo: "your-tripo-key"
  openai: "your-openai-key"
```

### 4. Run the Application

```bash
python main.py
```

The web interface will open at: **http://localhost:7860**

## First Generation

1. Open http://localhost:7860 in your browser
2. In the chat, type: "Generate a simple desk organizer"
3. Click "Generate 3D Models"
4. Wait for:
   - 2D preview generation (~10-30 seconds)
   - 3D model generation (~2-5 minutes)
   - Intelligent post-processing (~5-10 seconds)
5. Download your STL file from the "Ready to Print" tab!

## Using MCP with Claude Desktop (Optional)

If you want to use this from Claude Desktop:

### 1. Install MCP

```bash
pip install mcp
```

### 2. Configure Claude Desktop

Edit `~/.config/claude-desktop/config.json` (macOS/Linux) or `%APPDATA%\Claude\config.json` (Windows):

```json
{
  "mcpServers": {
    "3d-agent-generation": {
      "command": "python",
      "args": ["/absolute/path/to/3dAgentMCP/mcp_server/server.py"],
      "env": {
        "TRIPO_API_KEY": "your_key",
        "OPENAI_API_KEY": "your_key"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

After restart, you can use commands like:
```
Generate a 3D printable phone stand
```

Claude will automatically use the 3D generation tools!

## Troubleshooting

### "API key not found" error

- Check that you've added keys to `.env` or `config.yaml`
- Verify the keys are valid by testing them on provider websites

### "Module not found" error

```bash
pip install -r requirements.txt --upgrade
```

### Memory errors with large models

In `config.yaml`, reduce `face_limit`:
```yaml
generation:
  face_limit: 5000  # Lower value = smaller models
```

### Slow generation

This is normal! 3D generation takes 2-5 minutes per model. Be patient.

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check out [mcp_server/README.md](mcp_server/README.md) for MCP integration
- Experiment with different prompts and settings
- Try multi-object scenes: "A complete desktop workspace with organizer, phone stand, and pen holder"

## Tips for Best Results

### Writing Good Prompts

✅ Good:
- "A minimalist desk organizer with 3 compartments, rounded corners, modern design"
- "Cylindrical pen holder with 5 slots, 8cm tall, suitable for 3D printing"

❌ Avoid:
- "Make me something cool" (too vague)
- "A desk organizer but also a lamp and maybe a plant pot" (too complex, split into multiple objects)

### Settings Recommendations

**For fast testing:**
```yaml
face_limit: 5000
enable_2d_preview: false  # Skip preview for speed
```

**For high quality:**
```yaml
face_limit: 30000
use_image_to_3d: true  # Use 2D preview for better results
```

## Cost Estimates

Approximate costs per generation:

- **2D Preview (DALL-E 3)**: ~$0.04 per image
- **3D Model (Tripo3D)**: ~$0.15-0.50 per model
- **Total per object**: ~$0.20-0.55

Multi-object scenes cost proportionally more (e.g., 3 objects ≈ $0.60-1.65).

## Support

Having issues?

1. Check logs in `logs/3d_agent.log`
2. Review the [README.md](README.md) troubleshooting section
3. Open an issue on GitHub
4. Check API provider status pages

## Happy 3D Printing! 🎉

You're all set! Start generating amazing 3D printable models with AI.
