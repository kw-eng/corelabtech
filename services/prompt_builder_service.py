"""Server-owned Content Studio prompt construction.

Browser clients provide only the selected scene, character and output type.
Provider instructions and brand constraints remain on the server side.
"""

from __future__ import annotations


def build_generation_prompt(*, character_id: str, scene_id: str, output_type: str) -> str:
    """Return the internal prompt used for a validated generation request."""

    return "\n".join(
        (
            "CoreLabTech AI Content Studio",
            "",
            f"Character: {character_id}",
            f"Scene: {scene_id}",
            f"Output: {output_type}",
            "",
            "Use the official CoreLabTech character reference.",
            "Preserve character identity, facial features, hairstyle, body proportions, clothing, HR chest strap and smartwatch.",
            "Visual style: premium CoreLabTech commercial style; dark navy environment; electric blue accents; cyan highlights; professional cinematic lighting; modern technology aesthetic; realistic human proportions.",
            "Do not include commercial logos, watermarks, distorted anatomy, duplicated limbs, extra fingers, an incorrect face or a different hairstyle.",
        )
    )
