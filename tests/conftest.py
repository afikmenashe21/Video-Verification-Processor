import os
import subprocess
import tempfile

import pytest
from PIL import Image


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def sample_video(tmp_dir):
    """Generate a small synthetic video (3 seconds, 10fps) using ffmpeg."""
    path = os.path.join(tmp_dir, "test_video.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=blue:size=320x240:rate=10:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            path,
        ],
        capture_output=True,
        check=True,
    )
    return path


@pytest.fixture
def sample_ref_image(tmp_dir):
    """Generate a simple reference image."""
    path = os.path.join(tmp_dir, "ref_image.jpg")
    img = Image.new("RGB", (100, 100), color="red")
    img.save(path)
    return path
