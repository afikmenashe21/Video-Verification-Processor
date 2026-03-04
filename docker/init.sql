-- Video Verification Product Pipeline schema

CREATE TYPE job_status AS ENUM ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED');
CREATE TYPE task_status AS ENUM (
    'PENDING', 'APIFY_SUBMITTED', 'DOWNLOAD_READY', 'DOWNLOADING',
    'UPLOADED', 'PROCESSING', 'COMPLETED', 'FAILED', 'SKIPPED'
);
CREATE TYPE verdict_type AS ENUM ('PASS', 'FAIL', 'UNCERTAIN');

CREATE TABLE customers (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE products (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id       UUID NOT NULL REFERENCES customers(id),
    name              TEXT NOT NULL,
    reference_images  TEXT[] NOT NULL DEFAULT '{}',
    query_text        TEXT NOT NULL,
    default_model     TEXT NOT NULL DEFAULT 'gemini',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE verification_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id      UUID NOT NULL REFERENCES products(id),
    status          job_status NOT NULL DEFAULT 'PENDING',
    match_target    INT NOT NULL DEFAULT 3,
    match_count     INT NOT NULL DEFAULT 0,
    total_urls      INT NOT NULL DEFAULT 0,
    completed_count INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE video_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID NOT NULL REFERENCES verification_jobs(id),
    source_url      TEXT NOT NULL,
    status          task_status NOT NULL DEFAULT 'PENDING',
    apify_run_id    TEXT,
    download_url    TEXT,
    minio_bucket    TEXT,
    minio_key       TEXT,
    score           INT,
    confidence      FLOAT,
    verdict         verdict_type,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(job_id, source_url)
);

CREATE INDEX idx_products_customer ON products(customer_id);
CREATE INDEX idx_vj_product ON verification_jobs(product_id);
CREATE INDEX idx_vj_status ON verification_jobs(status);
CREATE INDEX idx_vt_job ON video_tasks(job_id);
CREATE INDEX idx_vt_apify_run ON video_tasks(apify_run_id);
CREATE INDEX idx_vt_status ON video_tasks(status);
