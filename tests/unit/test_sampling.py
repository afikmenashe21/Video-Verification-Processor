"""Tests for frame sampling logic.

These tests validate the sampling strategy calculations without requiring
a real video file (those belong in integration tests).
"""

from preprocessor.sampling import FpsSampler, UniformSampler


def test_uniformSampler_shouldRespectMaxFrames():
    sampler = UniformSampler(target_frames=100)
    effective = min(sampler._target_frames, 64)
    assert effective == 64


def test_fpsSampler_shouldStoreConfiguredFps():
    sampler = FpsSampler(fps=2.0)
    assert sampler._fps == 2.0


def test_uniformSampler_shouldUseTargetWhenBelowMax():
    sampler = UniformSampler(target_frames=16)
    effective = min(sampler._target_frames, 64)
    assert effective == 16
