/**
 * Shared plumbing for the three per-backend MCP servers
 * (server-gemini.ts / server-azure.ts / server-seedream.ts).
 *
 * Each backend server imports ONLY this file and its own backend module.
 * No cross-backend imports — the physical separation is the whole point:
 * agent harnesses cannot route to a different backend because the binary they
 * talking to has no code for one.
 */
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
export declare function makeLogger(name: string): (...args: unknown[]) => void;
export interface GeminiAccount {
    project: string;
    location: string;
    credentials: string;
    model: string;
    image_model: string;
    max_concurrency?: number;
}
export interface GeminiBackendConfig {
    accounts: GeminiAccount[];
}
export interface AzureBackendConfig {
    endpoint: string;
    deployment: string;
    api_version: string;
    api_key: string;
}
export interface SeedreamBackendConfig {
    base_url: string;
    api_key: string;
    model: string;
}
export interface SharedConfig {
    default_backend?: string;
    backends: {
        gemini?: GeminiBackendConfig;
        azure?: AzureBackendConfig;
        seedream?: SeedreamBackendConfig;
    };
}
export declare function loadConfig(): Promise<SharedConfig>;
export interface GeneratedImage {
    base64: string;
    mimeType: string;
    revisedPrompt?: string;
}
export declare function mimeForExt(path: string): string;
export declare function resizeRefForSend(rawBytes: Buffer, maxLongSide?: number): Promise<{
    bytes: Buffer;
    mime: string;
}>;
export declare const DEFAULT_OUTPUT_DIR: string;
export declare function saveImages(images: GeneratedImage[], outputDir: string): Promise<string[]>;
export declare function registerViewTool(server: McpServer): void;
export declare function renderGenerateResponse(images: GeneratedImage[], savedPaths: string[], backendLabel: string): {
    content: Array<{
        type: "text";
        text: string;
    } | {
        type: "image";
        data: string;
        mimeType: string;
    }>;
};
export declare function errorResponse(err: unknown): {
    content: Array<{
        type: "text";
        text: string;
    }>;
    isError: true;
};
