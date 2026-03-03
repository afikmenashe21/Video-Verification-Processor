from shared.domain import VideoVerificationJob


def test_shouldGenerateDeterministicKey():
    key1 = VideoVerificationJob.generate_idempotency_key("/video.mp4", ["/img1.jpg"], "find car")
    key2 = VideoVerificationJob.generate_idempotency_key("/video.mp4", ["/img1.jpg"], "find car")
    assert key1 == key2
    assert len(key1) == 16


def test_shouldProduceDifferentKeys_forDifferentInputs():
    key1 = VideoVerificationJob.generate_idempotency_key("/video.mp4", ["/img1.jpg"], "find car")
    key2 = VideoVerificationJob.generate_idempotency_key("/video.mp4", ["/img1.jpg"], "find truck")
    assert key1 != key2


def test_shouldSortImagePaths_forConsistentKeys():
    key1 = VideoVerificationJob.generate_idempotency_key("/v.mp4", ["/b.jpg", "/a.jpg"], "q")
    key2 = VideoVerificationJob.generate_idempotency_key("/v.mp4", ["/a.jpg", "/b.jpg"], "q")
    assert key1 == key2
