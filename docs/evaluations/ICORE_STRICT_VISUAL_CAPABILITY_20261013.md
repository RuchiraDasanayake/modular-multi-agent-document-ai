# One-request strict visual capability check

Classification: research evidence, keep. This check tested whether ICORE Luna 6
accepts the implemented strict response schema together with an original page
image and OCR geometry. It is not an extraction-quality or fresh OCR evaluation.

- Clean runtime commit: `2ec108b`.
- One previously used development receipt, SHA-256
  `28a8c9e154f9971aaae01212e395618460e610da9eca8f82d05b9b5277eb8c7c`.
- Corrected, previously sealed RapidOCR text and geometry were reused.
- One request, no retry, 8,192 maximum output tokens, 180-second timeout.
- Protocol SHA-256: `8017d3b31a781b915be6491f7fa752670d8ff50018c14b3ca13014da7fc36f40`.
- Private artifacts: `I:\DocAI-Benchmarks\visual-boundary-capability-v1`.

The provider finished with `stop`, no refusal or error. Local strict validation
passed for all eight requested fields; three linked cells were proposed. The
reported usage was 2,615 input and 591 output tokens, with 20.024 seconds of
provider latency. All non-null proposals remained in review. Dollar cost was not
measured. No gold labels were accessed by the runner.

This establishes one observed compatible response, not provider-wide schema
enforcement, correct values, or reliable table extraction. It used the visual
boundary before the full product workflow integration and before the EXIF
metadata correction. The source is an ordinary PNG without that orientation
issue. The next comparison must use fresh product intake and OCR on both arms,
the final code, and fixed schemas before scoring.
