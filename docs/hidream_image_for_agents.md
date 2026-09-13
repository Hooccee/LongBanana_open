# HiDream O1 Image — Reference for Agents

> Mechanical reference for the `hidream` text-to-image and reference-guided
> editing backend.

## Tool call

```text
generate_image(
  prompt=<non-empty string>,
  reference_images=[<absolute path>, ...] = [],  # 0–10
  output_dir=<absolute path>                      # optional
)
```

One call returns exactly one image. Inspect candidate files with
`view_reference_image(path)` before generation.

## Reference images

- **Hard maximum: 10 per call; an empty list enables text-only generation.**
- If more than ten files are available, select at most ten that best cover
  identity, layout, style, counts, and relationships.
- A background/base image counts toward the ten-image limit.
- Put the base image first, followed by the most important references.
- References are resized to a 1024-pixel maximum long side before transport.

## Prompt, output, and failures

Use a complete final-scene instruction and state which visual properties must
be retained from each selected reference. The tool saves the full 2048-pixel
PNG/JPEG under `output_dir`, returns the absolute path, and sends only a
compressed, aspect-ratio-preserving JPEG preview with a 768-pixel longest side
back to the Agent for reflection (no cropping or stretching).

The persistent GPU service may take several minutes; allow at least 20 minutes
and retry only after an explicit failure. Invalid counts, unreadable files,
HTTP errors, timeouts, and empty responses are tool errors. Parameters outside
the MCP schema are not accepted.
