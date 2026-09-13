# FireRed Agent Multi-Reference — Reference for Agents

> Mechanical reference for the `firered-agent` backend and its native
> multi-reference preprocessing.

## Tool call

```text
generate_image(
  prompt=<non-empty string>,
  reference_images=[<absolute path>, ...],  # exactly 1–64
  output_dir=<absolute path>                 # optional
)
```

One call returns exactly one image. Inspect files with
`view_reference_image(path)` before building the reference shortlist.

## Reference images

- **Hard minimum: 1; hard maximum: 64 per call.**
- Pass absolute paths in meaningful order; place the base/background first.
- One to three references go directly to FireRed inference.
- More than three activate ROI detection, cropping, background-aware grouping,
  stitching into two or three composites, and prompt/image-number recaption.
- References are resized to a 1024-pixel maximum long side for transport.

Do not add irrelevant files merely because the limit is high. Cover the
required identities, counts, layout, style, and relationships.

## Prompt, output, and failures

Describe the complete final composition and keep numbered-image language
consistent with `reference_images`. The tool saves the full-resolution
PNG/JPEG under `output_dir`, returns the absolute path, and shows a compressed
aspect-ratio-preserving JPEG preview with a 768-pixel longest side for
reflection (no cropping or stretching).

Multi-reference preprocessing may take several minutes; allow at least 20
minutes and retry only after an explicit failure. Invalid counts, file-read or
preprocessing failures, HTTP errors, timeouts, and empty responses are tool
errors. Parameters outside the schema are not accepted.
