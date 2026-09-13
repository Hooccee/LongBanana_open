import { type GeneratedImage } from "./_common.js";
export declare function generateWithGemini(params: {
    prompt: string;
    refs: string[];
}): Promise<GeneratedImage[]>;
