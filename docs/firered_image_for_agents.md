# FireRed Image Edit — Reference for Agents

> Mechanical reference for the `firered` backend. It describes the callable
> MCP surface and backend limits; reference selection and prompt composition
> remain the agent's responsibility.

## Tool call

```text
generate_image(
  prompt=<non-empty string>,
  reference_images=[<absolute path>, ...],  # exactly 1–3
  output_dir=<absolute path>                 # optional
)
```

One call returns exactly one image. Use `view_reference_image(path)` to inspect
candidate files before choosing the final list.

## Reference images

- **Hard minimum: 1; hard maximum: 3 per call.**
- Pass absolute paths only.
- If more files are available, select the one to three images that best
  preserve required identity, layout, and appearance.
- References are resized to a 1024-pixel maximum long side before transport.
- Use `firered-agent` when more than three references must be combined in one
  request.

## Prompt, output, and failures

Write a complete editing instruction describing the final image and make each
selected reference's role explicit. The tool saves the full-resolution
PNG/JPEG under `output_dir`, returns its absolute path, and shows a compressed
aspect-ratio-preserving JPEG preview with a 768-pixel longest side for
reflection (no cropping or stretching).

The persistent GPU service may take several minutes; allow at least 20 minutes
for the MCP request and retry only after an explicit failure. Invalid counts,
unreadable paths, HTTP failures, timeouts, and empty responses are tool errors.
Parameters outside the MCP schema are not accepted.
