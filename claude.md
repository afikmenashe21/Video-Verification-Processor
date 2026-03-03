# claude.md — Video Verification Service (Kafka → VLM Strategy → Scored Text Report)

## Goal

Build a **Python service** that consumes Kafka messages containing:

- `video_path` (string) — local path or URL/S3-style URI (implementation-specific)
- `images_path` (string[]) — reference images to match/verify against the video
- `verification_text_query` (string) — what we’re looking for (instructions, constraints, focus prompt)
- `default_model` (enum) — `smolvlm2` | `qwen2_5_vl` | `qwen3_omni` | …

The service runs a **video analysis job** using a selectable model runner (Strategy pattern) and writes a **text report** (and optionally JSON metadata) that includes:

- overall **score** (0–100) + confidence
- whether the **query** is satisfied
- whether **reference images** appear (and where, if possible)
- a **video description / summary**
- timestamps and evidence snippets when available
- model used + parameters + runtime stats

Must be:
- production-grade modular code
- testable, observable, idempotent
- Dockerized

---

## Non-Goals (for v1)

- Perfect “ground truth” verification (we provide probabilistic scoring)
- Real-time streaming inference
- Training/fine-tuning models (only inference)

---

## Architecture Overview

### Data flow

1. **Kafka Consumer** reads `VideoVerificationRequested` event.
2. **Job Orchestrator** validates input, resolves paths, assigns `job_id`.
3. **Model Strategy** chosen by `default_model` (or override policy).
4. **Preprocessing**:
   - sample frames/clips from the video
   - load reference images
   - construct model-specific prompt from `verification_text_query`
5. **Inference**:
   - query-driven video analysis
   - optional image-to-video similarity checks
6. **Scoring**:
   - aggregate signals (query match, image match, consistency, confidence)
7. **Output**:
   - write report to `output_dir/{job_id}.txt`
   - write structured metadata to `output_dir/{job_id}.json` (recommended)
8. **Ack / commit offset** only after output is persisted (at-least-once).

### Key design patterns

- **Strategy**: `ModelRunner` interface with `SmolVLM2Runner`, `Qwen25VLRunner`, `Qwen3OmniRunner`
- **Ports & Adapters** (light hexagonal):
  - Ports: `KafkaConsumerPort`, `StoragePort`, `ModelRunnerPort`
  - Adapters: `confluent_kafka`, `local_fs` / `s3`, `huggingface` / `qwen_api`

---

## Repository Layout (suggested)

```
video_verification_service/
  app/
    __init__.py
    main.py
    config.py
    logging.py

    api/                        # message schemas, DTOs
      __init__.py
      schemas.py                # pydantic models
      events.py                 # event names + versions

    core/                       # pure business logic (no IO)
      __init__.py
      domain.py                 # Job, Evidence, Score, Result
      scoring.py                # scoring aggregation
      prompts.py                # prompt builders (model-agnostic)
      policies.py               # model selection policy, thresholds
      errors.py                 # typed errors

    ports/                      # interfaces for IO
      __init__.py
      consumer.py               # ConsumerPort
      storage.py                # StoragePort
      model_runner.py           # ModelRunnerPort

    infra/                      # implementations (IO)
      __init__.py

      kafka/
        __init__.py
        consumer_confluent.py

      storage/
        __init__.py
        local_fs.py
        s3.py                    # optional

      models/
        __init__.py
        base.py                  # ModelRunner ABC
        registry.py              # runner registry + factory

        smolvlm2_runner.py
        qwen25_vl_runner.py
        qwen3_omni_runner.py

      video/
        __init__.py
        reader.py                # ffmpeg/pyav wrapper
        sampling.py              # frame sampling strategy
        hashing.py               # optional: video fingerprint

      observability/
        __init__.py
        metrics.py               # prometheus optional
        tracing.py               # opentelemetry optional

    service/                    # orchestration layer
      __init__.py
      handler.py                # message -> job -> result
      orchestrator.py           # end-to-end pipeline

  tests/
    unit/
    integration/

  docker/
    Dockerfile
    docker-compose.yml

  pyproject.toml
  README.md
```

---

## Message Contract (Kafka)

### Topic
- `video.verification.requested.v1`

### Payload (JSON)

```json
{
  "job_id": "optional-string-if-provided",
  "video_path": "/data/incoming/video.mp4",
  "images_path": ["/data/ref/img1.jpg", "/data/ref/img2.png"],
  "verification_text_query": "Find whether the person in the reference images appears in the video. Focus on the first 60 seconds. Also verify if a red car appears.",
  "default_model": "smolvlm2",
  "metadata": {
    "requested_by": "service-x",
    "priority": "normal"
  }
}
```

### Idempotency
- If `job_id` present: treat as idempotency key.
- If missing: generate deterministic key (e.g., hash of paths + query) and include in output.

---

## Output Contract

### Text report: `output/{job_id}.txt`

Recommended sections:
- Header: job_id, timestamps, model, runtime
- Overall verdict: PASS/FAIL/UNCERTAIN
- Score: 0–100, confidence: 0–1
- Evidence:
  - Query evidence: bullet points with timestamps (if model can provide)
  - Image evidence: per-image match confidence + timestamps (if available)
- Video summary
- Limitations / notes

### JSON metadata: `output/{job_id}.json` (recommended)

Fields:
- `job_id`
- `model`
- `inputs` (paths, query)
- `score`, `confidence`, `verdict`
- `evidence[]` (type, timestamp_range, text, confidence)
- `summary`
- `stats` (latency_ms, frames_sampled, tokens_used if available)

---

## Core Domain Objects (v1)

- `VideoVerificationJob`
  - `job_id`, `video_path`, `images_path`, `query`, `model`
- `Evidence`
  - `kind`: `QUERY_MATCH` | `IMAGE_MATCH` | `OBJECT_MATCH` | `OTHER`
  - `timestamp_start_s`, `timestamp_end_s`
  - `text`, `confidence`
- `VerificationResult`
  - `score_0_100`, `confidence_0_1`, `verdict`
  - `summary`
  - `evidence[]`
  - `raw_model_output` (optional, stored in json only)

---

## Strategy Pattern (Model Runners)

### Interface

`ModelRunnerPort` / `ModelRunner` methods:
- `name() -> str`
- `supports(video: bool, images: bool) -> bool`
- `analyze(job: VideoVerificationJob, frames: list[Frame], ref_images: list[Image]) -> ModelAnalysis`
- `healthcheck() -> RunnerHealth`

### Registry / Factory

- `ModelRunnerRegistry` maps enum → runner instance
- `ModelSelectionPolicy`:
  - default to requested model
  - fallback to another runner if unavailable
  - allow “auto” mode based on video length / GPU availability / cost

---

## Video Preprocessing

### Sampling strategy (default)

- extract frames at:
  - fixed FPS sampling (e.g., 1 fps) OR
  - uniform N frames (e.g., 32) OR
  - scene-change-based sampling (optional v2)
- optionally extract short clips around candidate timestamps (if model supports)

### Implementation choices

- Prefer **PyAV** or **ffmpeg-python** for robust decoding.
- Ensure deterministic sampling for idempotent results.

---

## Scoring (simple, explainable)

Score components (example):
- `query_match` (0–60)
- `image_match` (0–30)
- `consistency` (0–10)

Example rule:
- If query match confidence ≥ 0.75 → strong score boost
- If at least one ref image match ≥ 0.7 → PASS candidate
- Otherwise UNCERTAIN

Keep scoring purely in `core/scoring.py` so it’s testable and model-agnostic.

---

## Observability & Reliability

### Logging
- JSON logs (structlog or standard logging with formatter)
- Include: `job_id`, `model`, `topic`, `partition`, `offset`, `latency_ms`

### Metrics (optional but recommended)
- counters: jobs_consumed, jobs_succeeded, jobs_failed
- histogram: latency
- gauge: in_flight

### Failure handling
- poison pill handling: max retries per message
- DLQ topic: `video.verification.dlq.v1`
- commit offsets only after output persisted

---

## Concurrency Model

- One consumer process per container
- Use bounded worker pool for CPU-heavy preprocessing
- Model inference can be:
  - single-threaded per worker (GPU contention)
  - or queued via an internal async semaphore

---

## Configuration

Use `pydantic-settings`:

- `KAFKA_BOOTSTRAP_SERVERS`
- `KAFKA_TOPIC`
- `KAFKA_GROUP_ID`
- `OUTPUT_DIR`
- `MODEL_DEFAULT`
- `MODEL_DEVICE` (cpu/cuda)
- `FRAME_SAMPLING_FPS`
- `MAX_VIDEO_SECONDS` (guardrail)
- `QWEN_API_BASE_URL` / `QWEN_API_KEY` (if using managed endpoint)

---

## Docker

### Dockerfile expectations

- slim base image (python:3.11-slim)
- install ffmpeg / libav deps
- install torch/transformers as needed (separate GPU image optional)
- entrypoint: `python -m app.main`

### docker-compose.yml (dev)

- kafka + zookeeper (or redpanda)
- service container with volume mounts:
  - `/data/incoming`
  - `/data/ref`
  - `/data/output`

---

## Testing Strategy

### Unit tests
- scoring rules
- prompt builder
- model registry selection
- schema validation

### Integration tests
- kafka consume/produce with local broker
- end-to-end: small video fixture + stubbed runner

### Contract tests
- validate event schema versions

---

## Security & Privacy

- Avoid logging raw video frames or full prompts if sensitive
- Add PII-safe log masking for paths / queries if needed
- If using managed APIs: ensure outbound egress policy and secret handling

---

## Developer Workflow (Claude Code / Plan Mode)

### First step checklist
1. Scaffold project structure + `pyproject.toml`
2. Implement schemas + ports
3. Implement local fs + kafka consumer adapter
4. Implement video sampling (PyAV/ffmpeg wrapper)
5. Add a **MockRunner** to validate pipeline end-to-end
6. Add real runners incrementally (SmolVLM2 first)
7. Add scoring + report writer
8. Add docker + compose
9. Add integration test that runs in CI

### Plan-mode prompt (copy/paste)

Use this prompt when starting implementation:

- Read `claude.md` and create a step-by-step plan for building the service.
- Enforce ports/adapters separation.
- Start with MockRunner + deterministic sampling.
- Add production-grade logging and error handling.
- Provide commands to run locally and in Docker.
- Add at least 5 unit tests and 1 integration test.

---

## Model Runner Notes (pragmatic)

### SmolVLM2 runner
- Likely easiest locally via Hugging Face `transformers`
- Strength: lightweight, quick iteration
- Limitation: timestamps/grounding may be weaker; compensate via frame sampling and explicit prompts.

### Qwen2.5-VL runner
- Prefer if you need stronger video reasoning and longer context
- Implementation can be:
  - local weights (if feasible)
  - or managed endpoint adapter (recommended for simplicity)

### Qwen3-Omni runner
- Often best as managed endpoint (compute heavy)
- Consider cost/timeouts and implement circuit breakers + retries.

---

## Prompting Guidelines (model-agnostic)

Structure prompt as:

1. Task: “You are verifying whether X is present.”
2. Constraints: “Use reference images as identity anchors.”
3. Output format: JSON-like sections (so we can parse):
   - `verdict`, `confidence`, `timestamps`, `evidence`, `summary`
4. Safety: “If uncertain, say UNCERTAIN.”

Example template:

- **Instruction**:
  - Verify: {verification_text_query}
  - Use reference images as anchors.
  - If present, provide timestamps (start/end) and short evidence.
  - Output fields: verdict(PASS/FAIL/UNCERTAIN), confidence(0-1), evidence[], summary.

---

## Definition of Done (v1)

- Consumes Kafka messages reliably
- Runs at least **one real model runner** (SmolVLM2)
- Writes `{job_id}.txt` report + `{job_id}.json`
- Deterministic sampling + idempotent outputs
- Docker image builds and runs
- Basic tests passing in CI
