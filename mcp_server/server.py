"""
MCP (Model Context Protocol) Server for 3D Agent Generation System
Enables integration with Claude Desktop, Cursor, and other MCP clients
"""
import asyncio
import sys
import os
import base64
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try importing MCP, provide fallback
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp import types
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    print("Warning: MCP package not installed. Install with: pip install mcp")

from agents.coordinator import CoordinatorAgent
from utils.config import load_config
from utils.logger import get_logger

logger = get_logger("mcp_server")

# Initialize MCP server
app = Server("3d-agent-generation") if MCP_AVAILABLE else None

# Global coordinator instance
config = load_config()
coordinator = CoordinatorAgent(config)


if MCP_AVAILABLE:
    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        """List available tools for MCP clients"""
        return [
            types.Tool(
                name="generate_3d_model",
                description=(
                    "Generate a 3D printable model from text description with automatic "
                    "post-processing for 3D printing. Returns STL file path and metadata."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Text description of the 3D object to generate"
                        },
                        "style": {
                            "type": "string",
                            "enum": ["realistic", "cartoon", "low-poly", "technical"],
                            "description": "Visual style of the model",
                            "default": "realistic"
                        },
                        "generate_supports": {
                            "type": "boolean",
                            "description": "Auto-generate support structure recommendations",
                            "default": True
                        },
                        "optimize_orientation": {
                            "type": "boolean",
                            "description": "Optimize model orientation for printing",
                            "default": True
                        }
                    },
                    "required": ["description"]
                }
            ),

            types.Tool(
                name="generate_2d_preview",
                description=(
                    "Generate 2D preview image of an object before 3D generation. "
                    "Useful for confirming the concept before expensive 3D generation."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": "Description of the object"
                        },
                        "style": {
                            "type": "string",
                            "description": "Visual style",
                            "default": "realistic 3D render"
                        }
                    },
                    "required": ["description"]
                }
            ),

            types.Tool(
                name="analyze_printability",
                description=(
                    "Analyze a 3D model file for printability. "
                    "Provides detailed analysis and recommendations for orientation and supports."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "model_path": {
                            "type": "string",
                            "description": "Path to STL/OBJ/GLB file"
                        }
                    },
                    "required": ["model_path"]
                }
            ),

            types.Tool(
                name="plan_scene",
                description=(
                    "Plan a multi-object 3D scene. Breaks down complex scenes "
                    "into individual objects with optimized prompts."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "scene_description": {
                            "type": "string",
                            "description": "Description of the entire scene"
                        }
                    },
                    "required": ["scene_description"]
                }
            )
        ]

    @app.call_tool()
    async def call_tool(
        name: str,
        arguments: dict
    ) -> list[types.TextContent | types.ImageContent]:
        """Handle tool calls from MCP clients"""
        logger.info(f"MCP tool called: {name}")

        try:
            if name == "generate_3d_model":
                return await handle_generate_3d(arguments)

            elif name == "generate_2d_preview":
                return await handle_generate_2d(arguments)

            elif name == "analyze_printability":
                return await handle_analyze_printability(arguments)

            elif name == "plan_scene":
                return await handle_plan_scene(arguments)

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return [types.TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]


async def handle_generate_3d(args: dict) -> list[types.TextContent]:
    """Generate 3D model through coordinator"""
    description = args["description"]
    style = args.get("style", "realistic")

    logger.info(f"Generating 3D model: {description}")

    # Use quick generation
    result = await coordinator.generate_single_quick(
        prompt=f"{description}, {style} style",
        skip_preview=False,
        skip_postprocessing=False
    )

    if 'error' in result:
        return [types.TextContent(
            type="text",
            text=f"❌ Generation failed: {result['error']}"
        )]

    # Format response
    analysis = result.get('analysis', {})
    metadata = result.get('metadata', {})

    response_text = f"""
✅ 3D Model Generated Successfully!

**Object:** {result.get('object_name', 'model')}
**File:** {result['model_file']}

**Dimensions:**
- Volume: {metadata.get('volume_mm3', 0):.1f} mm³
- Bounding Box: {metadata.get('bounding_box_mm', [])}

**Print Estimates:**
- Print Time: ~{metadata.get('estimated_print_time_h', 0):.1f}h
- Material: ~{metadata.get('estimated_material_g', 0):.1f}g

**Processing Applied:**
{chr(10).join('- ' + log for log in metadata.get('processing_log', []))}

**AI Analysis:**
- Complexity: {analysis.get('complexity', 'unknown')}
- Print Difficulty: {analysis.get('print_difficulty', 'unknown')}
- Max Overhang: {analysis.get('max_overhang_angle', 0):.1f}°
- Support Strategy: {analysis.get('recommended_support_strategy', 'none')}

**Reasoning:**
{result.get('reasoning', 'No reasoning available')}
"""

    if metadata.get('warnings'):
        response_text += "\n\n⚠️ **Warnings:**\n"
        response_text += "\n".join('- ' + w for w in metadata['warnings'])

    return [types.TextContent(
        type="text",
        text=response_text
    )]


async def handle_generate_2d(args: dict) -> list[types.ImageContent | types.TextContent]:
    """Generate 2D preview"""
    description = args["description"]
    style = args.get("style", "realistic 3D render")

    logger.info(f"Generating 2D preview: {description}")

    preview = await coordinator.image_generator.generate_preview(
        prompt=description,
        style=style
    )

    # Read and encode image
    image_path = Path(preview['image_path'])
    if not image_path.exists():
        return [types.TextContent(
            type="text",
            text="❌ Failed to generate preview image"
        )]

    with open(image_path, 'rb') as f:
        image_data = f.read()

    image_b64 = base64.b64encode(image_data).decode()

    return [
        types.TextContent(
            type="text",
            text=f"✅ 2D Preview generated successfully!\n\n**Prompt used:** {preview.get('prompt_used', description)}"
        ),
        types.ImageContent(
            type="image",
            data=image_b64,
            mimeType="image/png"
        )
    ]


async def handle_analyze_printability(args: dict) -> list[types.TextContent]:
    """Analyze printability of existing model"""
    model_path = args["model_path"]

    logger.info(f"Analyzing printability: {model_path}")

    if not Path(model_path).exists():
        return [types.TextContent(
            type="text",
            text=f"❌ File not found: {model_path}"
        )]

    # Use postprocessor for analysis only
    analysis = await coordinator.postprocessor._analyze_model_geometry(model_path)

    analysis_text = f"""
📊 **Printability Analysis**

**File:** {model_path}

**Complexity:** {analysis.complexity.upper()}
**Print Difficulty:** {analysis.print_difficulty.upper()}

**Geometry:**
- Max Overhang: {analysis.max_overhang_angle:.1f}°
- Overhang Area: {analysis.overhang_area_mm2:.1f} mm²
- Contact Area: {analysis.contact_area_mm2:.1f} mm²
- Internal Cavities: {"Yes ⚠️" if analysis.has_internal_cavities else "No ✓"}

**Recommendations:**
- Printable without supports: {"Yes ✓" if analysis.is_printable_without_supports else "No ✗"}
- Recommended support strategy: **{analysis.recommended_support_strategy.upper()}**

**Optimal Orientation:** Calculated (apply with post-processing tool)
"""

    return [types.TextContent(
        type="text",
        text=analysis_text
    )]


async def handle_plan_scene(args: dict) -> list[types.TextContent]:
    """Plan multi-object scene"""
    scene_description = args["scene_description"]

    logger.info(f"Planning scene: {scene_description}")

    # Use planner
    plan = await coordinator.planner.plan_scene(scene_description)

    plan_text = f"📋 **Scene Plan for:** {scene_description}\n\n"

    for i, obj in enumerate(plan, 1):
        plan_text += f"**Object {i}: {obj['object']}**\n"
        plan_text += f"- Prompt: {obj['prompt']}\n"
        plan_text += f"- Priority: {obj['priority']}\n"
        if 'quantity' in obj and obj['quantity'] > 1:
            plan_text += f"- Quantity: {obj['quantity']}\n"
        plan_text += "\n"

    plan_text += "\n💡 Use `generate_3d_model` for each object to create the full scene."

    return [types.TextContent(
        type="text",
        text=plan_text
    )]


async def main():
    """Run MCP server"""
    if not MCP_AVAILABLE:
        print("ERROR: MCP package not available. Install with: pip install mcp")
        return

    logger.info("Starting MCP server for 3D Agent Generation System")

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    if not MCP_AVAILABLE:
        print("MCP package not installed. This server requires MCP to run.")
        print("Install with: pip install mcp")
        sys.exit(1)

    asyncio.run(main())
