/**
 * Gemini backend — Vertex AI REST + service-account JWT auth.
 * Isolated from Azure/Seedream code: not even importable from those modules.
 */
import { readFile } from "node:fs/promises";
import { isAbsolute, resolve } from "node:path";
import { createSign } from "node:crypto";
import { loadConfig, mimeForExt, makeLogger, resizeRefForSend, type GeneratedImage } from "./_common.js";

const log = makeLogger("image-gen-mcp-gemini");

interface ServiceAccountKey {
  private_key: string;
  client_email: string;
  token_uri?: string;
}

function base64UrlEncode(input: Buffer | string): string {
  const buf = typeof input === "string" ? Buffer.from(input) : input;
  return buf.toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

interface CachedToken { token: string; expiresAt: number; }
const _tokenCache = new Map<string, CachedToken>();

async function getAccessToken(credentialsPath: string): Promise<string> {
  const cached = _tokenCache.get(credentialsPath);
  if (cached && cached.expiresAt > Date.now() + 60_000) return cached.token;

  const raw = await readFile(credentialsPath, "utf-8");
  const key: ServiceAccountKey = JSON.parse(raw);

  const now = Math.floor(Date.now() / 1000);
  const header = { alg: "RS256", typ: "JWT" };
  const payload = {
    iss: key.client_email,
    scope: "https://www.googleapis.com/auth/cloud-platform",
    aud: key.token_uri ?? "https://oauth2.googleapis.com/token",
    iat: now,
    exp: now + 3600,
  };
  const encHeader = base64UrlEncode(JSON.stringify(header));
  const encPayload = base64UrlEncode(JSON.stringify(payload));
  const signingInput = `${encHeader}.${encPayload}`;
  const signer = createSign("RSA-SHA256");
  signer.update(signingInput);
  signer.end();
  const signature = signer.sign(key.private_key);
  const assertion = `${signingInput}.${base64UrlEncode(signature)}`;

  const tokenUrl = key.token_uri ?? "https://oauth2.googleapis.com/token";
  const form = new URLSearchParams({
    grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
    assertion,
  });
  const res = await fetch(tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
  });
  if (!res.ok) throw new Error(`OAuth token exchange failed: ${res.status} ${await res.text()}`);
  const body = await res.json() as { access_token: string; expires_in: number };
  _tokenCache.set(credentialsPath, {
    token: body.access_token,
    expiresAt: Date.now() + body.expires_in * 1000,
  });
  return body.access_token;
}

async function loadRefAsB64(ref: string): Promise<{ data: string; mime: string }> {
  const abs = isAbsolute(ref) ? ref : resolve(ref);
  const raw = await readFile(abs);
  // Long-side 1024 downscale before base64 (see _common.resizeRefForSend).
  const { bytes, mime } = await resizeRefForSend(raw);
  return { data: bytes.toString("base64"), mime };
}

let _accountIndex = 0;

export async function generateWithGemini(params: {
  prompt: string;
  refs: string[];
}): Promise<GeneratedImage[]> {
  const cfg = (await loadConfig()).backends.gemini;
  if (!cfg) throw new Error("Gemini config missing from image_gen_config.json");
  const accounts = cfg.accounts || [];
  if (!accounts.length) throw new Error("No Gemini accounts configured");

  const n = accounts.length;
  let lastErr: Error | null = null;
  for (let i = 0; i < n; i++) {
    const idx = (_accountIndex + i) % n;
    const acct = accounts[idx];
    try {
      const token = await getAccessToken(acct.credentials);
      const url = `https://aiplatform.googleapis.com/v1/projects/${acct.project}/locations/${acct.location}/publishers/google/models/${acct.image_model}:generateContent`;

      const parts: Array<Record<string, unknown>> = [{ text: params.prompt }];
      for (const r of params.refs) {
        const { data, mime } = await loadRefAsB64(r);
        parts.push({ inlineData: { mimeType: mime, data } });
      }
      const body = { contents: [{ role: "user", parts }] };

      log(`request (account=${acct.project})`, acct.image_model);
      const res = await fetch(url, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const rawText = await res.text();
      if (!res.ok) {
        lastErr = new Error(`Gemini API ${res.status}: ${rawText.slice(0, 400)}`);
        continue;
      }
      const parsed = JSON.parse(rawText);
      // Fair-comparison policy: one call -> one image. Vertex may
      // return multiple candidates; we take only the first inline
      // image part and discard the rest. Agent iterates by calling
      // generate_image again with an updated prompt.
      let first: GeneratedImage | null = null;
      outer: for (const cand of (parsed.candidates || [])) {
        for (const part of (cand.content?.parts || [])) {
          const inline = part.inlineData || part.inline_data;
          if (inline?.data) {
            first = {
              base64: inline.data,
              mimeType: inline.mimeType ?? inline.mime_type ?? "image/png",
            };
            break outer;
          }
        }
      }
      if (!first) {
        lastErr = new Error(`Gemini returned no image parts: ${rawText.slice(0, 400)}`);
        continue;
      }
      _accountIndex = (idx + 1) % n;
      return [first];
    } catch (err) {
      lastErr = err instanceof Error ? err : new Error(String(err));
    }
  }
  throw lastErr ?? new Error("Gemini: exhausted all accounts");
}
