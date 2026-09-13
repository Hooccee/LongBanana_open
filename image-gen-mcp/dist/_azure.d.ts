import { type GeneratedImage } from "./_common.js";
export declare function generateWithAzure(params: {
    prompt: string;
    refs: string[];
}): Promise<GeneratedImage[]>;
