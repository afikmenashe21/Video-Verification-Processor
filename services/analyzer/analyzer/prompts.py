from __future__ import annotations

_TEMPLATE = """You are a product verification assistant. Your task is to determine whether the product shown in the reference images appears in the provided video frames.

## Reference Images
{ref_images_section}

## Additional Instructions
{instructions_section}

## Analysis Guidelines
1. Compare the product in the reference images against what appears in each video frame.
2. Focus on: shape, color, branding, logos, materials, and distinguishing details.
3. A PASS means the same product (matching colorway, branding, and key details) is clearly visible in the video.
4. A FAIL means the product in the video is different from the reference images (wrong colorway, different branding, different model, etc.).
5. If you cannot determine with reasonable confidence, say UNCERTAIN — do not guess.
6. Provide specific evidence for your conclusion, referencing frame numbers and visual details.

## Required Output Format
Respond with the following JSON (no markdown fences):
{{
  "verdict": "PASS" or "FAIL" or "UNCERTAIN",
  "confidence": <float 0.0 to 1.0>,
  "evidence": [
    {{
      "kind": "IMAGE_MATCH" or "QUERY_MATCH" or "OBJECT_MATCH" or "OTHER",
      "text": "<description of what was found or why it does/doesn't match>",
      "confidence": <float 0.0 to 1.0>,
      "timestamp_start_s": <float or null>,
      "timestamp_end_s": <float or null>
    }}
  ],
  "summary": "<brief summary of whether the product matches>"
}}"""


def build_prompt(query: str, ref_image_count: int) -> str:
    if ref_image_count > 0:
        ref_section = (
            f"{ref_image_count} reference image(s) of the product are provided. "
            "These are the ground truth — compare the video frames against them."
        )
    else:
        ref_section = (
            "No reference images provided. Analyze video frames based on the instructions only."
        )

    instructions_section = query.strip() if query.strip() else "None."

    return _TEMPLATE.format(
        ref_images_section=ref_section,
        instructions_section=instructions_section,
    )
