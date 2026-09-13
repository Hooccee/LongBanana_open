/**
 * Volcengine Ark Seedream 4.0 backend.
 * Isolated: no imports from _gemini or _azure.
 */
import { readFile } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import { loadConfig, mimeForExt, makeLogger, resizeRefForSend, type GeneratedImage } from "./_common.js";

const log = makeLogger("image-gen-mcp-seedream");

export async function generateWithSeedream(params: {
  prompt: string;
  refs: string[];
  seed?: number;
}): Promise<GeneratedImage[]> {
  const cfg = (await loadConfig()).backends.seedream;
  if (!cfg) throw new Error("Seedream config missing from image_gen_config.json");
  const url = `${cfg.base_url.replace(/\/$/, "")}/images/generations`;

  // One call = one image. Agent-facing refine is explicit: call the
  // tool again with an updated prompt. Keeps the per-call contract
  // identical across gemini / azure / seedream for fair comparison.
  //
  // Seedream size: Mode 1 preset class ("2K" default, env-overridable).
  // Ark decides the aspect based on the prompt + refs. Trades anchor-
  // deterministic shape for Ark's own aspect judgment; 2K matches
  // Ark's vendor-recommended default (1K degrades face/text quality).
  // Env override SEEDREAM_SIZE accepts "1K" / "4K" / explicit WxH.
  const seedreamSize = (process.env.SEEDREAM_SIZE ?? "2K").trim() || "2K";
  const body: Record<string, unknown> = {
    model: cfg.model,
    prompt: params.prompt,
    n: 1,
    size: seedreamSize,
    response_format: "url",
    watermark: false,
  };
  if (params.seed !== undefined) body.seed = params.seed;

  if (params.refs.length) {
    const uris: string[] = [];
    for (const r of params.refs) {
      const abs = isAbsolute(r) ? r : resolve(r);
      const raw = await readFile(abs);
      // Long-side 1024 downscale before base64 (see _common.resizeRefForSend).
      const { bytes, mime } = await resizeRefForSend(raw);
      uris.push(`data:${mime};base64,${bytes.toString("base64")}`);
    }
    body.image = uris;
  }

  log("request", cfg.model,
      `refs=${params.refs.length} n=1 size=${seedreamSize} (Ark-auto aspect)`);
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${cfg.api_key}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const rawText = await res.text();
  if (!res.ok) throw new Error(`Seedream API ${res.status}: ${rawText.slice(0, 600)}`);
  const payload = JSON.parse(rawText);
  const items = payload.data || [];
  const imgs: GeneratedImage[] = [];
  for (const it of items) {
    if (it.url) {
      const dl = await fetch(it.url);
      if (!dl.ok) throw new Error(`Seedream download ${dl.status}`);
      const arr = Buffer.from(await dl.arrayBuffer());
      imgs.push({ base64: arr.toString("base64"), mimeType: "image/jpeg" });
    } else if (it.b64_json) {
      imgs.push({ base64: it.b64_json, mimeType: "image/png" });
    }
  }
  if (!imgs.length) throw new Error(`Seedream returned no image data: ${rawText.slice(0, 400)}`);
  return imgs;
}
