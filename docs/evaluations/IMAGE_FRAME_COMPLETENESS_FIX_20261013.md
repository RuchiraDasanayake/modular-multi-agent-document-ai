# Image-frame completeness — 13 October 2026

Classification: product intake and its shared schema-sample guard are **core / keep**.

## Defect and correction

Product image intake represented a TIFF or PNG as one page before checking its frame count. A multipage TIFF or
animated PNG could therefore reach first-frame OCR, especially on the short-scalar text route, while subsequent
coverage checks only saw that single page. The existing visual-request guard did not protect every route.

A two-frame TIFF regression reached an OCR failure sentinel before the fix. It now returns an explicit
`unsupported` document with `multi_frame_image_unsupported`, empty proposals and zero OCR/model calls. The same
shared check runs before schema-sample OCR. Two-frame TIFF and APNG fixtures cover both entry points; normal
single-frame TIFF, PNG, JPEG and BMP remain permitted. Multi-frame extraction is not implemented; split those
inputs into separate source files.

The change was tested with the product Python environment against image-frame, automatic extraction, schema
draft/preview and visual-boundary tests. Targeted Ruff checks passed. No provider calls or benchmark labels were
used. The frozen 2,000-original and paired 240-original checkouts are unchanged; their PDF and ordinary PNG
sources retain the previously registered implementation.
