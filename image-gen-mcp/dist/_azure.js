/**
 * Azure GPT-Image-1 backend — multipart /images/edits.
 * Isolated: no imports from _gemini or _seedream.
 */
import { readFile } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import { loadConfig, makeLogger, resizeRefForSend } from "./_common.js";
const log = makeLogger("image-gen-mcp-azure");
export async function generateWithAzure(params) {
    const cfg = (await loadConfig()).backends.azure;
    if (!cfg)
        throw new Error("Azure config missing from image_gen_config.json");
    if (!params.refs.length) {
        throw new Error("Azure GPT-Image-1 requires at least 1 reference image (images/edits endpoint).");
    }
    const endpoint = cfg.endpoint.endsWith("/") ? cfg.endpoint : cfg.endpoint + "/";
    const url = `${endpoint}openai/deployments/${cfg.deployment}/images/edits?api-version=${cfg.api_version}`;
    const form = new FormData();
    form.append("prompt", params.prompt);
    // One call = one image (fair-comparison policy across all 3 backends).
    // Agent refines by calling generate_image again with an updated prompt.
    // Output size/aspect is always "auto" — the Azure model decides it.
    // Agent cannot influence shape (matches gemini + seedream).
    form.append("n", "1");
    form.append("size", "auto");
    // `quality` is REQUIRED for this GPT-Image-1 deployment — omitting
    // it makes Azure black-hole the request (probed 2026-04-23, Read
    // timed out at 30s/75s/510s). Valid: low | medium | high | auto.
    form.append("quality", process.env.AZURE_QUALITY ?? "auto");
    // OpenAI gpt-image-1 family supports `moderation: auto | low` for
    // tuning content-filter strictness. Azure may silently drop unknown
    // fields, so we only send it when explicitly requested via env to
    // keep default request shape identical to before.
    const moderation = (process.env.AZURE_MODERATION ?? "").trim().toLowerCase();
    if (moderation === "auto" || moderation === "low") {
        form.append("moderation", moderation);
    }
    for (const r of params.refs) {
        const abs = isAbsolute(r) ? r : resolve(r);
        const raw = await readFile(abs);
        // Long-side 1024 downscale before upload (see _common.resizeRefForSend).
        const { bytes, mime } = await resizeRefForSend(raw);
        const blob = new Blob([new Uint8Array(bytes)], { type: mime });
        const baseName = (abs.split("/").pop() ?? "ref").replace(/\.[^.]+$/, "");
        const ext = mime === "image/jpeg" ? ".jpg" : ".png";
        form.append("image[]", blob, baseName + ext);
    }
    log("request", cfg.deployment, `refs=${params.refs.length} size=auto n=1`);
    const res = await fetch(url, {
        method: "POST",
        headers: { "Api-Key": cfg.api_key },
        body: form,
    });
    const raw = await res.text();
    if (!res.ok)
        throw new Error(`Azure API ${res.status}: ${raw.slice(0, 600)}`);
    const payload = JSON.parse(raw);
    const items = payload.data || [];
    const imgs = [];
    for (const it of items) {
        if (it.b64_json)
            imgs.push({ base64: it.b64_json, mimeType: "image/png" });
    }
    if (!imgs.length)
        throw new Error(`Azure: no b64_json in response: ${raw.slice(0, 400)}`);
    return imgs;
}
