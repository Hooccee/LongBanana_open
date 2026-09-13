import { type GeneratedImage } from "./_common.js";
export declare function generateWithSeedream(params: {
    prompt: string;
    refs: string[];
    seed?: number;
}): Promise<GeneratedImage[]>;
