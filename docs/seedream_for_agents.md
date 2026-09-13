# Seedream 4 (Ark) — Reference for Agents (opencode / hermes-agent)

> Mechanical reference for the `seedream` backend. Tells you **what the
> tool accepts, what it returns, and what it will silently ignore**.
> It does NOT tell you how to compose your prompt or when to iterate.
>
> Official doc: local copy at [`../seedream4_api.txt`](../seedream4_api.txt).
> Local router wrapper: `harness/image_gen/router.py` +
> `harness/image_gen/seedream.py`.

## 1. The call you make

One entry point per harness. Agents never touch Ark's HTTP surface
directly.

**Opencode** (MCP server `image-gen` → Python router → Ark):
```
generate_image(
  prompt=<str>,                     # required
  reference_images=[<abs path>, ...] = [],
  seed=<int>                        # optional
  output_dir=<abs path>             # optional; defaults under ~/.image-gen-mcp/generated
)
```
The backend is fixed server-side via `image_gen_config.json` and cannot be
overridden per-call.

**Hermes** (native tool → Python router → Ark):
```
image_generate(
  prompt=<str>,                                  # required
  reference_images=[<abs path>, ...] = []
)
```

One call = one image. To iterate, call the tool again with an updated
prompt.

Route: both paths land at
`POST https://ark.cn-beijing.volces.com/api/v3/images/generations`.

## 2. Reference images

From the official doc (doubao-seedream-4.0 row):

- **Max: 14 reference images per call.**
- Accepted formats: `jpeg`, `png` (4.5/4.0 also accept `webp`, `bmp`, `tiff`, `gif`).
- Per-image constraints:
  - aspect ratio (W/H) in `[1/16, 16]`
  - width and height each **> 14 px**
  - size **≤ 10 MB**
  - total pixels **≤ 6000 × 6000 = 36 000 000**
- Router down-samples each ref to long-side 1024 px before upload, then
  base64-encodes. You do not need to pre-process refs.

## 3. Prompt (official guidance)

> 建议不超过 **300 个汉字** 或 **600 个英文单词**。字数过多信息容易分散，
> 模型可能因此忽略细节，只关注重点，造成图片缺失部分元素。

(The doc does NOT state a hard prompt character limit; the 300/600 is
the vendor's recommendation.)

## 4. Output

- **Output format: JPEG** (doubao-seedream-4.0 is fixed to JPEG per doc;
  not customizable). Router returns `{bytes, mime="image/jpeg"}`; the
  harness wrapper writes the file under `output_dir`.
- Router fetches from the URL that Ark returns (doc: `url` format,
  **24-hour TTL on the link**); file lands locally so TTL doesn't bite
  downstream.
- Watermark: **doc default is `true`** ("AI生成" in bottom-right); **our
  router sends `watermark=false`** by default. Agents have no way to
  change this through the tool call.

## 5. What the router silently drops (will NOT reach Ark)

If you try to use any of these, they are ignored. Don't plan around them:

- `sequential_image_generation` (single image always; no groups)
- `sequential_image_generation_options.max_images`
- `tools` (`web_search`; 5.0-lite only)
- `stream`
- `guidance_scale` (not supported on 4.0)
- `output_format` (fixed JPEG on 4.0)
- `response_format` (router always uses `url` under the hood)
- `optimize_prompt_options` (fast / standard)
- `watermark` override through the tool call

### `seed` parameter

- **Opencode / MCP**: accepts `seed: int` (optional) and forwards to
  Ark. Per vendor doc, doubao-seedream-4.0 ignores this parameter
  server-side (only `doubao-seedream-3.0-t2i` honours it), so you will
  not get reproducible output on this deployment even though the call
  goes through without error.
- **Hermes**: no `seed` parameter in the tool schema.

## 6. Failure symptoms (what you might see)

Router-level only; no interpretation of the underlying cause. Error
codes themselves are documented at
<https://www.volcengine.com/docs/82379/1299023> (the doc does not
inline them here).

| Symptom | What it means mechanically |
|---|---|
| `RuntimeError: Seedream HTTP <code>: <body>` | Ark returned a non-2xx status; `<body>` carries `error.code` and `error.message`. |
| `RuntimeError: Seedream returned empty data` | Ark returned 2xx but `data[]` was empty. |
| `RuntimeError: Seedream item missing url/b64_json` | Ark returned 2xx with a `data[0]` that has neither `url` nor `b64_json`. |
