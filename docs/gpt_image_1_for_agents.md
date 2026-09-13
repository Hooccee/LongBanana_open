# GPT-Image-1 (Azure) — Reference for Agents (opencode / hermes-agent)

> Mechanical reference for the `azure` backend. Tells you **what the
> tool accepts, what it returns, and what it will silently ignore**.
> It does NOT tell you how to compose your prompt, how many refs to
> pick, or when to iterate.
>
> Official doc: local copy at [`../gpt_image_api.txt`](../gpt_image_api.txt).
> Local router wrapper: `harness/image_gen/router.py` +
> `harness/image_gen/azure.py`.

## 1. The call you make

One entry point per harness. Agents do not touch the Azure HTTP surface
directly.

**Opencode** (MCP server `image-gen` → Python router → Azure):
```
generate_image(
  prompt=<str>,                     # required
  reference_images=[<abs path>, ...] = [],
  output_dir=<abs path>             # optional; defaults under ~/.image-gen-mcp/generated
)
```
The backend is fixed server-side via `image_gen_config.json` and cannot be
overridden per-call.

**Hermes** (native tool → Python router → Azure):
```
image_generate(
  prompt=<str>,                                  # required
  reference_images=[<abs path>, ...] = []
)
```

One call = one image. To iterate, call the tool again with an updated
prompt.

## 2. Reference images

- **Router hard minimum: 1** (this backend goes through `/images/edits`,
  which has no text-only mode). Calling with `reference_images=[]`
  raises:
  `ValueError: Azure GPT-Image-1 uses /images/edits which requires at
  least 1 reference image.`
- **Official max: not stated.** The doc's own example uses 4 refs.
- Each entry: absolute path to PNG / JPEG. Router sends as `image[]`
  multipart parts.
- Refs are down-sampled to long-side 1024 px before upload.

## 3. Limitations (official doc §Limitations, verbatim)

> - Complex prompts may take up to 2 minutes to process.
> - Text rendering: significantly improved but still struggles with
>   precise text placement and clarity.
> - Consistency: may struggle to maintain visual consistency for
>   recurring characters / brand elements across multiple generations.
> - Composition control: may have difficulty placing elements precisely
>   in structured or layout-sensitive compositions.

## 4. Output

- Tool saves the PNG bytes into `output_dir/<filename>.png` and returns.
- Encoding on the wire: base64 (`b64_json`); router decodes before
  saving.
- Router HTTP timeout = 180 s; if exceeded, `requests.Timeout`
  propagates up.

## 5. What the router silently drops (will NOT reach Azure)

If you try to use any of these, they are ignored. Don't plan around them:

- `output_format` / `output_compression`
- `moderation` (official: `auto` / `low`)
- `background` (official: `opaque` / `auto`, `transparent` n/a)
- `mask`, `input_image_mask`, `input_fidelity`, `partial_images`

## 6. Failure symptoms (what you might see)

Observation-only; deciding what to do is on you. The router runs its
own retry policy (up to `AZURE_MAX_RETRIES=2`, exp backoff) for
transient errors, and will propagate non-transient errors up verbatim.

| Symptom | What it means |
|---|---|
| `ValueError: ... requires at least 1 reference image` | You passed an empty `reference_images` list |
| `400 duplicate_parameter` on `image` | Router bug — should not happen; already uses `image[]` |
| `400 content_policy_violation` / moderation 400 | Safety filter rejected prompt or output |
| `ConnectionError` / `ConnectionResetError(54)` | Network or overload; router retried already |
| `Read timed out (read timeout=180)` | Call took >180 s |
