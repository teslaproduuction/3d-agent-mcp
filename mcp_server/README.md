# MCP Server for 3D Agent Generation

This directory contains the Model Context Protocol (MCP) server implementation for the 3D Agent Generation System. This allows integration with Claude Desktop, Cursor, Cline, and other MCP-compatible tools.

## Features

The MCP server exposes 4 tools:

1. **generate_3d_model** - Full 3D generation with intelligent post-processing
2. **generate_2d_preview** - Quick 2D preview generation
3. **analyze_printability** - Analyze existing 3D models
4. **plan_scene** - Multi-object scene planning

## Setup for Claude Desktop

### 1. Install MCP Package

```bash
pip install mcp
```

### 2. Configure Claude Desktop

Edit your Claude Desktop configuration file:

**macOS/Linux:**
```bash
nano ~/.config/claude-desktop/config.json
```

**Windows:**
```
%APPDATA%\Claude\config.json
```

Add the following configuration:

```json
{
  "mcpServers": {
    "3d-agent-generation": {
      "command": "python",
      "args": ["/path/to/3dAgentMCP/mcp_server/server.py"],
      "env": {
        "TRIPO_API_KEY": "your_tripo_api_key",
        "OPENAI_API_KEY": "your_openai_api_key",
        "ANTHROPIC_API_KEY": "your_anthropic_api_key"
      }
    }
  }
}
```

Replace `/path/to/3dAgentMCP` with the actual path to your project.

### 3. Restart Claude Desktop

After configuration, restart Claude Desktop to load the MCP server.

## Usage Examples

### In Claude Desktop

Once configured, you can use the tools naturally in conversation:

```
User: Generate a 3D printable desk organizer

Claude: I'll generate that for you using the 3D generation tool.
[Uses generate_3d_model tool]

Claude: ✅ I've generated your desk organizer!

The model is optimized for 3D printing:
- File: outputs/models/model_abc123.stl
- Volume: 45,230 mm³
- Estimated print time: ~3.2h
- Material needed: ~56g PLA

The model was automatically:
- Oriented for minimal overhangs (12° max)
- No supports needed!
- Positioned on build plate

You can download the STL and slice it in your preferred slicer.
```

### 2D Preview First

```
User: Show me a preview of a smartphone stand before generating the 3D model

Claude: Let me generate a 2D preview first.
[Uses generate_2d_preview tool]

Claude: Here's a preview of the smartphone stand. Would you like me to proceed with 3D generation?
```

### Analyze Existing Model

```
User: Can you analyze this STL file for 3D printing? /path/to/model.stl

Claude: I'll analyze that model for printability.
[Uses analyze_printability tool]

Claude: Here's the printability analysis:
- Complexity: MEDIUM
- Print Difficulty: EASY
- Max Overhang: 38.5°
- Printable without supports: Yes ✓
...
```

### Plan Complex Scene

```
User: I want to create a desk setup with multiple objects

Claude: Let me plan that scene for you.
[Uses plan_scene tool]

Claude: I've broken down your desk setup into these objects:
1. Desk organizer base
2. Pen holder (x3)
3. Phone stand
4. Cable management clip (x5)

Would you like me to generate all of these?
```

## Setup for Cursor / Cline

For Cursor or Cline, add similar configuration to their respective MCP configuration files:

**Cursor:**
```json
// In Cursor settings
{
  "mcp": {
    "servers": {
      "3d-agent-generation": {
        "command": "python",
        "args": ["/path/to/3dAgentMCP/mcp_server/server.py"]
      }
    }
  }
}
```

## Troubleshooting

### Server Not Starting

1. Check that MCP is installed: `pip show mcp`
2. Verify Python path in config
3. Check logs in Claude Desktop console

### API Key Errors

Ensure all required API keys are set:
- TRIPO_API_KEY (required)
- OPENAI_API_KEY (required for DALL-E and GPT-4)
- ANTHROPIC_API_KEY (optional, for Claude LLM)

### Path Issues

Use absolute paths in the configuration, not relative paths.

## Development

To test the MCP server directly:

```bash
cd mcp_server
python server.py
```

This will start the server in stdio mode, waiting for MCP protocol messages.

## More Information

- [MCP Protocol Specification](https://spec.modelcontextprotocol.io/)
- [Claude Desktop MCP Guide](https://docs.anthropic.com/claude/docs/mcp)
