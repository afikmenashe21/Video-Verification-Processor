# Video Verification Processor

A **microservices-based video verification pipeline** that verifies product videos against reference images using Vision Language Models (VLMs). The system supports two modes of operation:

1. **Product Pipeline** (full orchestration) — Submit a product with ~30 TikTok/Instagram URLs, automatically extract download links via Apify, download videos, verify each against reference images, and stop early once enough videos match.
2. **Direct Pipeline** (core verification) — Send a single video verification request via Kafka for frame extraction, VLM inference, and scoring.

## Architecture

```
                          PRODUCT PIPELINE                                    CORE VERIFICATION PIPELINE
                          ================                                    ==========================

POST /api/v1/jobs
  { product_id, urls[] }
        |
        v
+------------+   Apify HTTP API   +---------+
| SUBMITTER  |------------------->[  Apify  ]
| (FastAPI)  |  start actor runs  |         |
|            |  + register hooks  |         |
+------------+                    +---------+
      |                                |
      | INSERT job + tasks             | webhook POST
      v                                v
 [Postgres] <------- +----------+   video.download   +-----------+   video.verification   +--------------+   +----------+   +--------+
                     |  GATEWAY  |   .ready.v1        | DOWNLOADER|   .requested.v1        | PREPROCESSOR |-->| ANALYZER |-->| SCORER |
                     | (FastAPI) |-------------------->|           |----------------------->|  (existing)  |   |(existing)|   |(exist.)|
                     +----------+                     | * skip?   |  (existing topic)      +--------------+   +----------+   +--------+
                                                      | * download|                                                               |
                                                      | * MinIO   |                                                               |
                                                      +-----------+                                                               |
                                                                                               video.verification.completed.v1    |
                                                                                                                                  v
 [Postgres] <----------------------------------------------------------------------------------------------------------+------------------+
   * update score/verdict                                                                                              | COMPLETION       |
   * increment match_count                                                                                             | HANDLER          |
   * if match_count >= 3: SKIP remaining                                                                               | * record result  |
                                                                                                                       | * early terminate|
                                                                                                                       +------------------+
```

### Services

| Service | Type | Responsibility |
|---------|------|---------------|
| **Submitter** | FastAPI (HTTP) | Accepts product verification jobs, creates DB records, triggers Apify actor runs |
| **Gateway** | FastAPI (HTTP) | Receives Apify webhooks, fetches download URLs from Apify dataset, publishes download-ready events |
| **Downloader** | Kafka consumer | Downloads MP4 files, uploads to MinIO, publishes to core pipeline |
| **Preprocessor** | Kafka consumer | Reads video, samples frames (FPS-based), saves as JPEG to shared volume |
| **Analyzer** | Kafka consumer | Loads frames, calls VLM API (Gemini/GPT-4o/Claude), publishes analysis results |
| **Scorer** | Kafka consumer | Computes score (0-100), determines verdict, writes `.txt` and `.json` reports |
| **Completion Handler** | Kafka consumer | Records verification results in Postgres, handles early termination |

### Shared Library

The `shared/` package contains domain types, error hierarchy, event schemas (Pydantic), database helpers, and base configuration.

## Product Pipeline Flow

### How It Works

1. **Setup**: A customer and product are registered in Postgres with reference images and a verification query.
2. **Submit**: `POST /api/v1/jobs` with the product ID and a list of ~30 TikTok/Instagram URLs.
3. **Apify**: The Submitter triggers an Apify actor run for each URL to extract the direct video download link. Each run includes a webhook pointing to the Gateway.
4. **Webhook**: When Apify finishes, it POSTs to the Gateway. The Gateway fetches the download URL from the Apify dataset API and publishes a `VideoDownloadReady` event.
5. **Download**: The Downloader consumes the event, downloads the MP4, uploads to MinIO, and publishes a `VideoVerificationRequested` event into the core pipeline.
6. **Verify**: The core pipeline (Preprocessor -> Analyzer -> Scorer) processes the video against the product's reference images.
7. **Complete**: The Completion Handler records the score/verdict in Postgres and increments the match counter.
8. **Early Termination**: Once `match_count >= match_target` (default 3), all remaining in-flight tasks are marked `SKIPPED` and the job is marked `COMPLETED`.

### Early Termination

The pipeline is optimized for cost efficiency. Given ~30 URLs per product, we only need 3 PASS verdicts:

- **Gateway**: If a webhook arrives for a `SKIPPED` task, it returns 200 (no-op).
- **Downloader**: If a download-ready event arrives for a `SKIPPED` task, the message is dropped.
- **Completion Handler**: If a result arrives for a task already in terminal state, it's discarded (idempotent).
- **In-flight work**: Videos already in the core pipeline are processed normally; the result is simply discarded by the Completion Handler if the job is already done.

### Task State Machine

```
PENDING --> APIFY_SUBMITTED --> DOWNLOAD_READY --> DOWNLOADING --> UPLOADED --> PROCESSING --> COMPLETED
    |              |                   |                |              |            |
    +--------------+-------------------+--------------+-+--------------+------------+---> SKIPPED (early termination)
    |              |                   |                |              |            |
    +--------------+-------------------+--------------+-+--------------+------------+---> FAILED (error at any step)
```

## Repository Layout

```
Video-Verification-Processor/
├── shared/                              # Shared library (domain, errors, events, config, db)
│   ├── pyproject.toml
│   └── shared/
│       ├── domain.py                    # Verdict, Evidence, ModelAnalysis, VerificationResult
│       ├── errors.py                    # ServiceError, DownloadError, ApifyError, ValidationError
│       ├── events.py                    # Kafka topic constants + Pydantic message schemas
│       ├── config.py                    # BaseServiceConfig, DatabaseConfig
│       └── db.py                        # psycopg connection helper
│
├── services/
│   ├── submitter/                       # Product Pipeline: Job submission + Apify trigger
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── submitter/
│   │       ├── main.py                  # FastAPI app (POST /api/v1/jobs, GET status)
│   │       ├── config.py               # SubmitterConfig
│   │       ├── handler.py              # Job creation, Apify orchestration
│   │       ├── schemas.py              # CreateJobRequest, JobResponse, TaskResponse
│   │       └── apify_client.py         # Apify Run Actor API client
│   │
│   ├── gateway/                         # Product Pipeline: Apify webhook receiver
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── gateway/
│   │       ├── main.py                  # FastAPI app (POST /api/v1/webhooks/apify)
│   │       ├── config.py               # GatewayConfig
│   │       └── handler.py              # Webhook processing, Apify dataset fetch
│   │
│   ├── downloader/                      # Product Pipeline: Video download + MinIO upload
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── downloader/
│   │       ├── main.py                  # Kafka consumer loop
│   │       ├── config.py               # DownloaderConfig (MinIO, timeouts)
│   │       └── handler.py              # Download, upload, publish to core pipeline
│   │
│   ├── completion_handler/              # Product Pipeline: Result recording + early termination
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── completion_handler/
│   │       ├── main.py                  # Kafka consumer loop
│   │       ├── config.py               # CompletionHandlerConfig
│   │       └── handler.py              # Score recording, match counting, SKIP logic
│   │
│   ├── preprocessor/                    # Core Pipeline: Video -> Frames
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── preprocessor/
│   │       ├── main.py                  # Kafka consumer loop
│   │       ├── config.py               # PreprocessorConfig
│   │       ├── handler.py              # Frame extraction orchestration
│   │       ├── reader.py               # Video metadata extraction (PyAV)
│   │       └── sampling.py             # FpsSampler, UniformSampler
│   │
│   ├── analyzer/                        # Core Pipeline: Frames -> VLM Analysis
│   │   ├── Dockerfile
│   │   ├── pyproject.toml
│   │   └── analyzer/
│   │       ├── main.py                  # Kafka consumer loop + runner registration
│   │       ├── config.py               # AnalyzerConfig (API keys, model settings)
│   │       ├── handler.py              # Load frames, run inference, cleanup, publish
│   │       ├── base.py                  # Image encoding utilities (base64, resize)
│   │       ├── prompts.py              # VLM prompt builder
│   │       ├── parsing.py              # JSON/regex output parser
│   │       └── runners/
│   │           ├── port.py              # ModelRunnerPort (ABC)
│   │           ├── registry.py          # Lazy factory registry
│   │           ├── openai_runner.py     # GPT-4o
│   │           ├── anthropic_runner.py  # Claude
│   │           ├── gemini_runner.py     # Gemini 2.5 Flash
│   │           └── mock_runner.py       # Deterministic test runner
│   │
│   └── scorer/                          # Core Pipeline: Analysis -> Score + Report
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── scorer/
│           ├── main.py                  # Kafka consumer loop
│           ├── config.py               # ScorerConfig
│           ├── handler.py              # Score, write reports, publish completion
│           ├── scoring.py              # Scoring algorithm (0-100 + verdict)
│           └── report_writer.py        # Text report + JSON metadata formatters
│
├── docker/
│   ├── docker-compose.yml               # All infra + all 7 services
│   └── init.sql                         # PostgreSQL schema (customers, products, jobs, tasks)
│
├── tests/
│   ├── conftest.py                      # Shared fixtures (synthetic video, ref image)
│   ├── unit/                            # Unit tests for all services
│   └── integration/                     # Integration tests (full pipeline with MockRunner)
│
├── test_resources/                      # Test videos + reference images
│   ├── videos/
│   └── images/
│
├── output/                              # Generated reports ({job_id}.txt, {job_id}.json)
├── pyproject.toml                       # Root project config + pytest settings
├── .env                                 # API keys (not committed)
└── .gitignore
```

## Kafka Topics

| Topic | Publisher | Consumer | Schema |
|-------|-----------|----------|--------|
| `video.download.ready.v1` | Gateway | Downloader | `VideoDownloadReady` |
| `video.verification.requested.v1` | Downloader (or direct input) | Preprocessor | `VideoVerificationRequested` |
| `video.frames.extracted.v1` | Preprocessor | Analyzer | `FramesExtracted` |
| `video.analysis.completed.v1` | Analyzer | Scorer | `AnalysisCompleted` |
| `video.verification.completed.v1` | Scorer | Completion Handler | `VerificationCompleted` |
| `video.verification.dlq.v1` | Any service | — | Raw message + error |

## PostgreSQL Schema

The product pipeline uses 4 tables:

- **`customers`** — Customer entities (id, name)
- **`products`** — Product definitions with `reference_images` (TEXT[]), `query_text`, and `default_model`
- **`verification_jobs`** — One job per product verification batch (tracks `match_count`, `match_target`, `status`)
- **`video_tasks`** — One task per URL in a job (tracks state through the full lifecycle)

See `docker/init.sql` for the complete schema.

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
- Apify API token + actor ID (for TikTok/Instagram URL extraction)

### 1. Configure Environment

```bash
cp .env.example .env
```

Add the following to `.env`:
```dotenv
# VLM API keys (at least one required)
GEMINI_API_KEY=your-gemini-key
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

# Apify (required for product pipeline)
APIFY_API_TOKEN=apify_api_xxx
APIFY_ACTOR_ID=your-actor-id
```

### 2. Start Infrastructure + Services

```bash
cd docker
docker compose up -d
```

This starts:
- **Redpanda** (Kafka-compatible broker) on port 9092
- **PostgreSQL** on port 5432 (auto-runs `init.sql`)
- **MinIO** on port 9000 (console on 9001, auto-creates `videos` bucket)
- **All 7 microservices** (submitter:8000, gateway:8001, preprocessor, analyzer, scorer, downloader, completion-handler)

### 3. Create Topics

```bash
docker exec docker-redpanda-1 rpk topic create \
  video.download.ready.v1 \
  video.verification.requested.v1 \
  video.frames.extracted.v1 \
  video.analysis.completed.v1 \
  video.verification.completed.v1 \
  video.verification.dlq.v1
```

### 4. Seed a Customer + Product

Before submitting a job, you need a customer and product in Postgres:

```bash
docker exec -i docker-postgres-1 psql -U postgres -d verification <<'SQL'
INSERT INTO customers (id, name)
VALUES ('aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa', 'Test Customer');

INSERT INTO products (id, customer_id, name, reference_images, query_text, default_model)
VALUES (
  'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  'Air Jordan 1 Low',
  ARRAY['/data/images/jordan_1.jpeg', '/data/images/jordan_2.jpeg'],
  'Verify product match',
  'gemini'
);
SQL
```

> **Note**: Reference image paths must be accessible inside the Analyzer container. The `docker-compose.yml` mounts `test_resources/images/` to `/data/images/` in both the preprocessor and analyzer.

### 5. Expose Gateway for Apify Webhooks

Apify needs to reach the Gateway's webhook endpoint over the public internet. Use a tunnel:

```bash
# Option A: localtunnel
npx localtunnel --port 8001
# Returns: https://some-slug.loca.lt

# Option B: ngrok
ngrok http 8001
# Returns: https://xxxx.ngrok-free.app
```

Update the Submitter's `WEBHOOK_BASE_URL` environment variable to the tunnel URL. In `docker-compose.yml`:

```yaml
submitter:
  environment:
    WEBHOOK_BASE_URL: https://some-slug.loca.lt  # your tunnel URL
```

Then restart the submitter: `docker compose restart submitter`

### 6. Submit a Verification Job

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    "urls": [
      "https://www.tiktok.com/@user1/video/123456",
      "https://www.tiktok.com/@user2/video/789012",
      "https://www.tiktok.com/@user3/video/345678"
    ]
  }'
```

Response:
```json
{
  "job_id": "cdef1234-...",
  "product_id": "bbbbbbbb-...",
  "status": "IN_PROGRESS",
  "match_target": 3,
  "match_count": 0,
  "total_urls": 3,
  "completed_count": 0,
  "created_at": "2026-03-04T..."
}
```

### 7. Monitor Progress

```bash
# Job status (match_count, completed_count, status)
curl http://localhost:8000/api/v1/jobs/{job_id}

# Individual task statuses
curl http://localhost:8000/api/v1/jobs/{job_id}/tasks

# Watch Kafka events
docker exec docker-redpanda-1 rpk topic consume video.verification.completed.v1

# Check Postgres directly
docker exec docker-postgres-1 psql -U postgres -d verification \
  -c "SELECT id, status, score, verdict FROM video_tasks WHERE job_id = '{job_id}';"

# View generated reports
ls output/
cat output/{task_id}.txt
```

## Direct Pipeline (Without Product Pipeline)

You can also send individual verification requests directly via Kafka, bypassing the product pipeline entirely:

```bash
echo '{"job_id":"test-1","video_path":"/data/videos/vid_1.mp4","images_path":["/data/images/jordan_1.jpeg","/data/images/jordan_2.jpeg"],"query":"Verify product match","model":"gemini"}' | \
  docker exec -i docker-redpanda-1 rpk topic produce video.verification.requested.v1 --key="test-1"

# Check results
cat output/test-1.txt
cat output/test-1.json

# Read completion events
docker exec docker-redpanda-1 rpk topic consume video.verification.completed.v1 --num 1
```

## Output Format

Each verified video produces:

- **Text report** (`output/{task_id}.txt`) — Human-readable with verdict, score, evidence, summary
- **JSON metadata** (`output/{task_id}.json`) — Structured data with score, confidence, evidence list, stats

### Example Report

```
============================================================
VIDEO VERIFICATION REPORT
============================================================

Job ID:      bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb
Model:       gemini
Video:       /data/videos/job-id/task-id.mp4
Query:       Verify product match
Ref Images:  2
Runtime:     7264 ms

----------------------------------------
VERDICT & SCORE
----------------------------------------
Verdict:     PASS
Score:       90 / 100
Confidence:  1.00

----------------------------------------
EVIDENCE
----------------------------------------
  1. [IMAGE_MATCH] (conf=1.00)
     The sneaker shown in all video frames is an Air Jordan 1 Low,
     matching the silhouette of the reference images...

----------------------------------------
SUMMARY
----------------------------------------
The product in the video frames is a clear match...

============================================================
```

## Configuration Reference

### Submitter

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/verification` | Postgres connection string |
| `APIFY_API_TOKEN` | — | Apify API token |
| `APIFY_ACTOR_ID` | — | Apify actor ID for TikTok extraction |
| `WEBHOOK_BASE_URL` | `http://gateway:8001` | Public URL for Apify to call back to the Gateway |
| `MATCH_TARGET` | `3` | Number of PASS verdicts needed to complete a job |
| `HTTP_PORT` | `8000` | HTTP listen port |

### Gateway

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Postgres connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `APIFY_API_TOKEN` | — | Apify API token (for fetching dataset items) |
| `HTTP_PORT` | `8001` | HTTP listen port |

### Downloader

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Postgres connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `video.download.ready.v1` | Input topic |
| `KAFKA_GROUP_ID` | `downloader-service` | Consumer group |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO endpoint |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `videos` | MinIO bucket name |
| `VIDEO_BASE_DIR` | `/data/videos` | Local video storage path |
| `DOWNLOAD_TIMEOUT_S` | `120` | HTTP download timeout |

### Completion Handler

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://...` | Postgres connection string |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Kafka broker address |
| `KAFKA_TOPIC` | `video.verification.completed.v1` | Input topic |
| `KAFKA_GROUP_ID` | `completion-handler-service` | Consumer group |

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

- **PASS verdict** (model says match) -> base 65 + evidence bonus (up to +30)
- **FAIL verdict** (model says mismatch) -> base 25 - evidence penalty
- **UNCERTAIN** -> 30-55 range based on average evidence confidence

Evidence quality bonus considers:
- Image match confidence (up to 15 pts)
- Query match confidence (up to 8 pts)
- Evidence consistency (2 pts if confidence spread < 0.2)

Final verdict thresholds: score >= 60 + confidence >= 0.5 -> PASS, score < 35 -> FAIL, otherwise UNCERTAIN.

## Reliability

- **At-least-once delivery**: offsets committed only after output is persisted
- **Retry with DLQ**: failed messages retried up to 3 times, then sent to dead letter queue
- **Idempotency**: deterministic job IDs via SHA256 hash; DB updates use `WHERE status NOT IN (terminal states)`
- **Early termination**: once match target is reached, remaining tasks are skipped across all pipeline stages
- **Frame cleanup**: analyzer deletes extracted frames after inference to prevent disk exhaustion
- **Graceful shutdown**: SIGTERM/SIGINT handlers for clean consumer/producer shutdown
- **Row-level locking**: Postgres `UPDATE ... RETURNING` serializes concurrent match_count increments

## Local Development

```bash
# Install all packages in editable mode
pip install -e shared/
pip install -e services/preprocessor/
pip install -e services/analyzer/
pip install -e services/scorer/
pip install -e services/submitter/
pip install -e services/gateway/
pip install -e services/downloader/
pip install -e services/completion_handler/

# Run tests
pytest tests/ -v
```

## Testing

```bash
# All tests
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
| Completion Handler | 5 | Match counting, early termination, idempotency |
| Gateway | 7 | Webhook parsing, skip logic, URL extraction |
| Submitter | 5 | Request validation, response schemas |
| Download Events | 3 | New event schemas, backward compatibility |
| E2E Pipeline | 1 | Full 3-stage pipeline with MockRunner + synthetic video |
| E2E Real | 2 | Full pipeline with real test videos |

## Infrastructure

| Component | Image | Ports | Purpose |
|-----------|-------|-------|---------|
| Redpanda | `redpandadata/redpanda:v24.1.1` | 9092, 29092 | Kafka-compatible event broker |
| PostgreSQL | `postgres:16-alpine` | 5432 | Job/task state, product catalog |
| MinIO | `minio/minio:latest` | 9000 (API), 9001 (console) | Video object storage |

### Useful Commands

```bash
# View all services
docker compose ps

# View logs for a specific service
docker compose logs -f submitter
docker compose logs -f gateway
docker compose logs -f completion-handler

# Inspect Postgres
docker exec docker-postgres-1 psql -U postgres -d verification \
  -c "SELECT status, count(*) FROM video_tasks GROUP BY status;"

# Inspect MinIO (browse uploaded videos)
# Open http://localhost:9001 — login: minioadmin / minioadmin

# Inspect Kafka topics
docker exec docker-redpanda-1 rpk topic list
docker exec docker-redpanda-1 rpk topic consume video.verification.completed.v1 --num 5

# Stop everything
docker compose down -v
```
