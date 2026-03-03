# Video Verification Processor

A **microservices-based video verification pipeline** that analyzes videos against reference images using Vision Language Models (VLMs). The system consumes Kafka messages, extracts frames from videos, runs VLM inference (OpenAI GPT-4o, Anthropic Claude, Google Gemini), scores the results, and produces structured reports.

## Architecture

The system is split into **3 independent services** communicating via Kafka, plus a shared library:

```
VideoVerificationRequested (Kafka input)
        │
        ▼
┌──────────────────┐   video.frames.extracted.v1   ┌──────────────┐   video.analysis.completed.v1   ┌────────────┐
│  PREPROCESSOR    │ ──────────────────────────────▶│   ANALYZER   │ ──────────────────────────────▶│   SCORER   │
│                  │                                │              │                                │            │
│ • consume request│                                │ • load frames│                                │ • score    │
│ • read video     │                                │ • load refs  │                                │ • verdict  │
│ • sample frames  │                                │ • call VLM   │                                │ • report   │
│ • save to disk   │                                │ • cleanup    │                                │ • output   │
│ • publish paths  │                                │ • publish    │                                │            │
└──────────────────┘                                └──────────────┘                                └────────────┘
                                                                                                        │
                                                                                              video.verification.completed.v1
```

### Services

| Service | Responsibility | Kafka In | Kafka Out |
|---------|---------------|----------|-----------|
| **Preprocessor** | Reads video, samples frames (FPS-based), saves as JPEG to shared volume | `video.verification.requested.v1` | `video.frames.extracted.v1` |
| **Analyzer** | Loads frames from disk, calls VLM API, cleans up frames after inference | `video.frames.extracted.v1` | `video.analysis.completed.v1` |
| **Scorer** | Computes score (0-100), determines verdict (PASS/FAIL/UNCERTAIN), writes `.txt` and `.json` reports | `video.analysis.completed.v1` | `video.verification.completed.v1` |

### Shared Library

The `shared/` package contains domain types, error hierarchy, event schemas (Pydantic), and base configuration — installed as a dependency by each service.

## Repository Layout

```
Video-Verification-Processor/
├── shared/                              # Shared library (domain, errors, events, config)
│   ├── pyproject.toml
│   └── shared/
│       ├── domain.py                    # Verdict, Evidence, ModelAnalysis, VerificationResult, etc.
│       ├── errors.py                    # ServiceError hierarchy
│       ├── events.py                    # Kafka topic constants + Pydantic message schemas
│       └── config.py                    # Base Kafka configuration
│
├── services/
│   ├── preprocessor/                    # Service 1: Video → Frames
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── preprocessor/
│   │       ├── main.py                  # Kafka consumer loop
│   │       ├── config.py                # PreprocessorConfig
│   │       ├── handler.py               # Message handling + frame extraction orchestration
│   │       ├── reader.py                # Video metadata extraction (PyAV)
│   │       └── sampling.py              # FpsSampler, UniformSampler
│   │
│   ├── analyzer/                        # Service 2: Frames → VLM Analysis
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── analyzer/
│   │       ├── main.py                  # Kafka consumer loop + runner registration
│   │       ├── config.py                # AnalyzerConfig (API keys, model settings)
│   │       ├── handler.py               # Load frames, run inference, cleanup, publish
│   │       ├── base.py                  # Image encoding utilities (base64, resize)
│   │       ├── prompts.py               # VLM prompt builder
│   │       ├── parsing.py               # JSON/regex output parser
│   │       └── runners/
│   │           ├── port.py              # ModelRunnerPort (ABC)
│   │           ├── registry.py          # Lazy factory registry
│   │           ├── openai_runner.py     # GPT-4o
│   │           ├── anthropic_runner.py  # Claude
│   │           ├── gemini_runner.py     # Gemini 2.5 Flash
│   │           └── mock_runner.py       # Deterministic test runner
│   │
│   └── scorer/                          # Service 3: Analysis → Score + Report
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── scorer/
│           ├── main.py                  # Kafka consumer loop
│           ├── config.py                # ScorerConfig
│           ├── handler.py               # Score, write reports, publish completion
│           ├── scoring.py               # Scoring algorithm (0-100 + verdict)
│           └── report_writer.py         # Text report + JSON metadata formatters
│
├── docker/
│   └── docker-compose.yml               # Redpanda + all 3 services
│
├── tests/
│   ├── conftest.py                      # Shared fixtures (synthetic video, ref image)
│   ├── unit/                            # 25 unit tests
│   └── integration/                     # 3 integration tests (full pipeline with MockRunner)
│
├── test_resources/                      # Test videos + reference images
│   ├── videos/
│   └── images/
│
├── pyproject.toml                       # Root project config + pytest settings
├── .env                                 # API keys (not committed)
├── .gitignore
└── .dockerignore
```

## Kafka Topics

| Topic | Direction | Schema |
|-------|-----------|--------|
| `video.verification.requested.v1` | Input | `VideoVerificationRequested` |
| `video.frames.extracted.v1` | Preprocessor → Analyzer | `FramesExtracted` |
| `video.analysis.completed.v1` | Analyzer → Scorer | `AnalysisCompleted` |
| `video.verification.completed.v1` | Output | `VerificationCompleted` |
| `video.verification.dlq.v1` | Dead letter queue | Raw message + error |

### Input Message

```json
{
  "job_id": "abc123",
  "video_path": "/data/videos/video.mp4",
  "images_path": ["/data/images/ref1.jpg", "/data/images/ref2.jpg"],
  "query": "Verify product colorway and branding match",
  "model": "gemini"
}
```

### Output

Each job produces:
- **Text report** (`output/{job_id}.txt`) — human-readable with verdict, score, evidence, summary
- **JSON metadata** (`output/{job_id}.json`) — structured data with score, confidence, evidence list, stats
- **Kafka event** on `video.verification.completed.v1` — score, verdict, output file paths

## Supported Models

| Model | Runner | Config Env Vars |
|-------|--------|----------------|
| Gemini 2.5 Flash | `gemini_runner.py` | `GEMINI_API_KEY`, `GEMINI_MODEL` |
| GPT-4o | `openai_runner.py` | `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` |
| Claude Sonnet | `anthropic_runner.py` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| Mock (testing) | `mock_runner.py` | — |

Models are registered via a lazy factory registry — runners are only instantiated on first use.

## Getting Started

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- ffmpeg (for local development)
- At least one VLM API key (Gemini, OpenAI, or Anthropic)

### Local Development Setup

```bash
# Install shared library + all services
pip install -e shared/
pip install -e services/preprocessor/
pip install -e services/analyzer/
pip install -e services/scorer/

# Configure API keys
cp .env.example .env  # Add your API keys

# Run tests
pytest tests/
```

### Docker Compose (Full Pipeline)

```bash
# Start Redpanda + all 3 services
cd docker
docker compose up -d

# Create topics
docker exec docker-redpanda-1 rpk topic create \
  video.verification.requested.v1 \
  video.frames.extracted.v1 \
  video.analysis.completed.v1 \
  video.verification.completed.v1 \
  video.verification.dlq.v1

# Send a verification request
echo '{"job_id":"test-1","video_path":"/data/videos/vid_1.mp4","images_path":["/data/images/jordan_1.jpeg","/data/images/jordan_2.jpeg"],"query":"Verify product match","model":"gemini"}' | \
  docker exec -i docker-redpanda-1 rpk topic produce video.verification.requested.v1 --key="test-1"

# Check results
cat output/test-1.json

# Read completion events
docker exec docker-redpanda-1 rpk topic consume video.verification.completed.v1 --num 1

# Stop
docker compose down -v
```

## Configuration

Each service reads configuration from environment variables via `pydantic-settings`.

### Preprocessor

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `video.verification.requested.v1` | Input topic |
| `KAFKA_GROUP_ID` | `preprocessor-service` | Consumer group |
| `FRAMES_BASE_DIR` | `/data/frames` | Directory to save extracted frames |
| `FRAME_SAMPLING_FPS` | `1.0` | Frame extraction rate |
| `FRAME_SAMPLING_MAX_FRAMES` | `64` | Maximum frames per video |
| `MAX_VIDEO_SECONDS` | `300` | Video duration guardrail |

### Analyzer

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_TOPIC` | `video.frames.extracted.v1` | Input topic |
| `KAFKA_GROUP_ID` | `analyzer-service` | Consumer group |
| `MODEL_DEFAULT` | `gemini` | Default VLM model |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `GEMINI_API_KEY` | — | Google Gemini API key |

### Scorer

| Variable | Default | Description |
|----------|---------|-------------|
| `KAFKA_TOPIC` | `video.analysis.completed.v1` | Input topic |
| `KAFKA_GROUP_ID` | `scorer-service` | Consumer group |
| `OUTPUT_DIR` | `/data/output` | Report output directory |

## Scoring Algorithm

The scoring system maps VLM analysis to a 0-100 score with a verdict:

- **PASS verdict** (model says match) → base 65 + evidence bonus (up to +30)
- **FAIL verdict** (model says mismatch) → base 25 − evidence penalty
- **UNCERTAIN** → 30-55 range based on average evidence confidence

Evidence quality bonus considers:
- Image match confidence (up to 15 pts)
- Query match confidence (up to 8 pts)
- Evidence consistency (2 pts if confidence spread < 0.2)

Final verdict thresholds: score ≥ 60 + confidence ≥ 0.5 → PASS, score < 35 → FAIL, otherwise UNCERTAIN.

## Reliability

- **At-least-once delivery**: offsets committed only after output is persisted
- **Retry with DLQ**: failed messages retried up to 3 times, then sent to dead letter queue
- **Idempotency**: deterministic job IDs via SHA256 hash of (video_path, images_path, query)
- **Frame cleanup**: analyzer deletes extracted frames after inference to prevent disk exhaustion
- **Graceful shutdown**: SIGTERM/SIGINT handlers for clean consumer/producer shutdown

## Testing

```bash
# All tests (25 unit + 3 integration)
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests (requires ffmpeg for synthetic video generation)
pytest tests/integration/ -v
```

### Test Coverage

| Area | Tests | What's covered |
|------|-------|---------------|
| Domain | 3 | Idempotency key generation, determinism |
| Parsing | 6 | JSON parsing, markdown fences, regex fallback, clamping |
| Scoring | 8 | PASS/FAIL/UNCERTAIN scoring, evidence bonuses, edge cases |
| Prompts | 4 | Prompt building with/without ref images |
| Sampling | 3 | Sampler configuration |
| Schemas | 5 | Pydantic validation for input events |
| Registry | 3 | Model runner registration and lookup |
| E2E Pipeline | 1 | Full 3-stage pipeline with MockRunner + synthetic video |
| E2E Real | 2 | Full pipeline with real test videos |
