# Gemini Image-Gen — Reference for Agents (opencode / hermes-agent)

> Mechanical reference for the `gemini` backend. Tells you **what the
> tool accepts, what it returns, and what it will silently ignore**.
> It does NOT tell you how to compose your prompt or when to iterate —
> those are your calls.
>
> Official doc: <https://ai.google.dev/gemini-api/docs/image-generation>
> (fetched 2026-04-22). Local router wrapper: `harness/image_gen/router.py`
> + `harness/image_gen/gemini.py`.

## 1. The call you make

One entry point per harness. Agents do not touch the Vertex SDK
directly.

**Opencode** (MCP server `image-gen` → Python router → Vertex):
```
generate_image(
  prompt=<str>,                     # required
  reference_images=[<abs path>, ...] = [],
  output_dir=<abs path>             # optional; defaults under ~/.image-gen-mcp/generated
)
```
The backend is fixed server-side via `image_gen_config.json` and cannot be
overridden per-call.

**Hermes** (native tool → Python router → Vertex):
```
image_generate(
  prompt=<str>,                                  # required
  reference_images=[<abs path>, ...] = []
)
```

One call = one image. To iterate, call the tool again with an updated
prompt.

## 2. Reference images

- **Official max: 14 per call.**
  - `gemini-3.1-flash-image-preview` (our deployment): up to 10 objects +
    up to 4 characters, totaling 14.
  - Behavior at >14: doc does not state.
- Each entry: absolute path to an image file (router opens via
  `PIL.Image.open`).
- Refs are down-sampled to long-side 1024 px before upload (keeps payloads
  bounded under concurrency).
- Router sends refs as a flat list in the order you passed them. No
  object/character tagging.

## 3. Prompt (official doc, direct quote)

> Describe the scene, don't just list keywords. The model's core
> strength is its deep language understanding. A narrative, descriptive
> paragraph will almost always produce a better [result].

## 4. Output

- Router returns `{bytes, mime}` from the SDK; the harness wrapper
  writes the file under `output_dir`.
- **SynthID watermark is applied to every generated image** (official).

## 5. What the router silently drops (will NOT reach Vertex)

If you try to use any of these, they are ignored. Don't plan around them:

- `thinkingLevel` (official param with values `minimal` / `high`)
- watermark-removal hints
- Anything not in the call signature above

## 6. Failure symptoms (what you might see)

Router-level only; no interpretation of the underlying cause.

| Symptom | What it means mechanically |
|---|---|
| `RuntimeError: Gemini returned None (exhausted all accounts)` | `client.generate_image()` returned `None` after its internal 5-retry loop across every configured account. |
| Any `google.api_core` / network exception propagated up | The SDK's own retry did not cover it; the router re-raises verbatim. |
