from analyzer.prompts import build_prompt


def test_shouldIncludeInstructions_whenBuilding():
    prompt = build_prompt("Check for the red car", ref_image_count=0)
    assert "Check for the red car" in prompt
    assert "No reference images" in prompt


def test_shouldIncludeRefImageContext_whenImagesProvided():
    prompt = build_prompt("Verify identity", ref_image_count=3)
    assert "3 reference image(s)" in prompt
    assert "ground truth" in prompt
    assert "Verify identity" in prompt


def test_shouldIncludeOutputFormat():
    prompt = build_prompt("test query", ref_image_count=0)
    assert '"verdict"' in prompt
    assert '"confidence"' in prompt
    assert '"evidence"' in prompt


def test_shouldFocusOnProductComparison():
    prompt = build_prompt("some instructions", ref_image_count=2)
    assert "product" in prompt.lower()
    assert "compare" in prompt.lower()
