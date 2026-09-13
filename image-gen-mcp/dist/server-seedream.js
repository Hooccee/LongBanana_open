#!/usr/bin/env node
/**
 * MCP server dedicated to the Seedream (Volcengine Ark) image-gen backend.
 * Only imports _seedream + _common — physically cannot route to Gemini or Azure.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { DEFAULT_OUTPUT_DIR, errorResponse, makeLogger, registerViewTool, renderGenerateResponse, saveImages, } from "./_common.js";
import { generateWithSeedream } from "./_seedream.js";
const log = makeLogger("image-gen-mcp-seedream");
const server = new McpServer({ name: "image-gen-mcp-seedream", version: "3.0.0" });
server.tool("generate_image", "Generate a single image via Seedream 4.0 (Volcengine Ark). Refs are posted as base64 data URIs in the 'image' array. Each call returns exactly one image; to iterate/refine, call this tool again with an updated prompt.", {
    prompt: z.string().describe("Text description / edit instruction."),
    reference_images: z.array(z.string()).default([]).describe("Absolute paths to reference images (jpeg/png/webp/bmp/tiff/gif). Empty = pure text-to-image."),
    seed: z.number().int().optional().describe("Seed (doubao-seedream-4.0 ignores server-side per vendor doc; 3.0-t2i honours it)."),
    output_dir: z.string().optional().describe("Directory to save images. Default: ~/.image-gen-mcp/generated"),
}, async (params) => {
    try {
        const outDir = params.output_dir || DEFAULT_OUTPUT_DIR;
        const images = await generateWithSeedream({
            prompt: params.prompt,
            refs: params.reference_images,
            seed: params.seed,
        });
        const saved = await saveImages(images, outDir);
        return renderGenerateResponse(images, saved, "seedream (Ark)");
    }
    catch (err) {
        return errorResponse(err);
    }
});
registerViewTool(server);
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    log("server running on stdio (seedream-only, v3)");
}
main().catch((err) => {
    console.error("Fatal:", err);
    process.exit(1);
});
