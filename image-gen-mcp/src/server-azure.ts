#!/usr/bin/env node
/**
 * MCP server dedicated to the Azure GPT-Image-1 image-gen backend.
 * Only imports _azure + _common — physically cannot route to Gemini or Seedream.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import {
  DEFAULT_OUTPUT_DIR,
  errorResponse,
  makeLogger,
  registerViewTool,
  renderGenerateResponse,
  saveImages,
} from "./_common.js";
import { generateWithAzure } from "./_azure.js";

const log = makeLogger("image-gen-mcp-azure");
const server = new McpServer({ name: "image-gen-mcp-azure", version: "3.0.0" });

server.tool(
  "generate_image",
  "Generate a single image via Azure GPT-Image-1 (/images/edits). Requires >=1 reference_images. Supplied refs are posted as multipart image[] parts. Each call returns exactly one image; to iterate/refine, call this tool again with an updated prompt. Output size/aspect is decided by the Azure model.",
  {
    prompt: z.string().describe("Text description / edit instruction."),
    reference_images: z.array(z.string()).default([]).describe(
      "Absolute paths to reference images. At least 1 required by this endpoint.",
    ),
    output_dir: z.string().optional().describe(
      "Directory to save images. Default: ~/.image-gen-mcp/generated",
    ),
  },
  async (params) => {
    try {
      const outDir = params.output_dir || DEFAULT_OUTPUT_DIR;
      const images = await generateWithAzure({
        prompt: params.prompt,
        refs: params.reference_images,
      });
      const saved = await saveImages(images, outDir);
      return renderGenerateResponse(images, saved, "azure (GPT-Image-1)");
    } catch (err) {
      return errorResponse(err);
    }
  },
);

registerViewTool(server);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  log("server running on stdio (azure-only, v3)");
}
main().catch((err) => {
  console.error("Fatal:", err);
  process.exit(1);
});
