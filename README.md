# Transaction Processing Pipeline

An asynchronous transaction processing pipeline built with FastAPI, Celery, Redis, and PostgreSQL that cleans dirty financial transaction data and performs outlier/anomaly detection.

---

## Architecture Diagram

The system operates asynchronously using a job queue architecture:

```
[ Client (Browser/cURL) ]
          │ (POST /jobs/upload, GET /jobs/{id}/status, GET /jobs/{id}/results)
          ▼
   [ FastAPI Web App ]
     │             │ (Enqueue)
     │             ▼
     │      [ Redis Broker ]
     │             │
     │             ▼ (Fetch Job)
     │      [ Celery Worker ]
     │             │
     │             ▼ (Save Results)
     └──────► [ PostgreSQL DB ]
```

---

## Setup & Execution

The entire pipeline is containerized and starts with a single command.

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### Quick Start
1. **Clone/Copy the project directory**
2. **Create a local `.env` file** from `.env.example` if you want to override default settings.
3. **Start the pipeline**:
   ```bash
   docker compose up --build
   ```
   This command automatically builds the containers, runs PostgreSQL/Redis, waits for database availability, executes Alembic migrations, and boots FastAPI and the Celery worker.

---

## API Documentation

FastAPI provides an interactive Swagger UI. Once the services are running, access it at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Endpoint Reference & Example cURL Commands

#### 1. Upload CSV File
- **Endpoint**: `POST /jobs/upload`
- **Request**:
  ```bash
  curl -X POST "http://localhost:8000/jobs/upload" \
       -H "accept: application/json" \
       -H "Content-Type: multipart/form-data" \
       -F "file=@transactions.csv"
  ```
- **Response**:
  ```json
  {
    "job_id": "8a7c29e2-2be5-4c07-b248-cb0fa0b86a41",
    "status": "pending"
  }
  ```

#### 2. Get Job Status
- **Endpoint**: `GET /jobs/{job_id}/status`
- **Request**:
  ```bash
  curl -X GET "http://localhost:8000/jobs/8a7c29e2-2be5-4c07-b248-cb0fa0b86a41/status"
  ```
- **Response (processing)**:
  ```json
  {
    "job_id": "8a7c29e2-2be5-4c07-b248-cb0fa0b86a41",
    "status": "processing",
    "summary": null
  }
  ```
- **Response (completed)**:
  ```json
  {
    "job_id": "8a7c29e2-2be5-4c07-b248-cb0fa0b86a41",
    "status": "completed",
    "summary": {
      "total_spend_inr": 150000.50,
      "total_spend_usd": 2500.00,
      "top_merchants": [
        {"merchant": "Flipkart", "total_spend": 10882.55},
        {"merchant": "Swiggy", "total_spend": 8900.20}
      ],
      "anomaly_count": 2
    }
  }
  ```

#### 3. Get Job Results
- **Endpoint**: `GET /jobs/{job_id}/results`
- **Request**:
  ```bash
  curl -X GET "http://localhost:8000/jobs/8a7c29e2-2be5-4c07-b248-cb0fa0b86a41/results"
  ```
- **Response**:
  ```json
  {
    "cleaned_transactions": [
      {
        "txn_id": "TXN1065",
        "date": "2024-09-04",
        "merchant": "Flipkart",
        "amount": 10882.55,
        "currency": "INR",
        "status": "SUCCESS",
        "category": "Shopping",
        "account_id": "ACC003",
        "is_anomaly": false,
        "anomaly_reason": null,
        "id": "c1a01b2a-71b3-469b-9830-ec38c4146bb1",
        "job_id": "8a7c29e2-2be5-4c07-b248-cb0fa0b86a41"
      }
    ],
    "flagged_anomalies": [
      {
        "txn_id": "TXN1054",
        "date": "2024-02-05",
        "merchant": "Swiggy",
        "amount": 11325.79,
        "currency": "USD",
        "status": "SUCCESS",
        "category": "Food",
        "account_id": "ACC004",
        "is_anomaly": true,
        "anomaly_reason": "CURRENCY_MERCHANT_MISMATCH",
        "id": "e0b1c2d3-1234-5678-9abc-def012345678",
        "job_id": "8a7c29e2-2be5-4c07-b248-cb0fa0b86a41"
      }
    ],
    "category_breakdown": {
      "Shopping": 12,
      "Food": 8,
      "Utilities": 4
    }
  }
  ```

#### 4. List All Jobs
- **Endpoint**: `GET /jobs`
- **Request**:
  ```bash
  curl -X GET "http://localhost:8000/jobs?status=completed"
  ```
- **Response**:
  ```json
  [
    {
      "job_id": "8a7c29e2-2be5-4c07-b248-cb0fa0b86a41",
      "filename": "transactions.csv",
      "status": "completed",
      "row_count": 95,
      "created_at": "2026-06-12T19:22:40Z"
    }
  ]
  ```

---

## Environment Variables

The service supports configuration through environment variables or a local `.env` file. Example variables include:

```env
DATABASE_URL=postgresql://postgres:postgres@db:5432/transactions
REDIS_URL=redis://redis:6379/0
UPLOAD_DIR=/app/uploads
GEMINI_API_KEY=your-gemini-api-key
GEMINI_API_URL=https://gemini.googleapis.com/v1/models/gemini-1.5-flash:generateText
```

## Local Development & Testing

### Running Tests
To execute the test suite (covering API routes, data cleaning helpers, duplicate removal, and anomaly detection):

1. **Activate local virtualenv**:
   ```bash
   source venv/bin/activate
   ```
2. **Run Pytest**:
   ```bash
   PYTHONPATH=. pytest -v
   ```

---

## Assumptions & Design Choices

1. **Median Anomaly Base**:
   - The median outlier rule (`amount > 3 × median`) is computed based on transactions *inside the current batch/job*. This allows self-contained batch updates and prevents cross-job database read bottleneck during cleaning.
2. **Missing fields fallbacks**:
   - If `category` is missing, it is filled with `"Uncategorised"`.
   - If `txn_id` is missing, we auto-generate a unique ID prefixed with `TXN_GEN_` using UUIDv4.
3. **USD Domestic Mismatch**:
   - Swiggy, Ola, and IRCTC are flagged as anomalies if the currency is exactly `"USD"`.
4. **Deduplication Definition**:
   - Duplicates are identified as rows where *all* raw columns are identical. The count of duplicate rows is excluded from DB writes and reported back to job metrics.

---

## Scalability Discussion (100x Traffic Increases)

If transaction traffic scales by 100×, the current single-server Docker Compose architecture will face performance bottlenecks in the following areas:

### Expected Bottlenecks
1. **Network I/O & Disk Bottleneck on Uploads**:
   - Uploading large CSVs directly to the FastAPI container local disk degrades storage throughput, depleting disk space and memory during multi-multipart handling.
2. **Celery Worker Concurrency**:
   - A single Celery worker processing long-running CSV parses and database inserts will back up the Redis queue.
3. **Database Write Congestion**:
   - Single-connection SQLAlchemy transactions insert records one-by-one. 100x volume will locks tables and spike CPU usage.
4. **Single-Point Redis Queue**:
   - Memory limits on a single Redis node risk queue crashes if tasks pile up.

### Enterprise Redesign Strategy

To support 100x scale, we recommend migrating to the following architecture:

```
                  ┌─────────────────┐
                  │   API Gateway   │ (Kong/Apigee - Rate Limiting & Auth)
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Load Balancer   │
                  └────────┬────────┘
                           ▼
            ┌─────────────────────────────┐
            │   Kubernetes Pods (FastAPI) │ (HPA auto-scaled on CPU/Memory)
            └──────────────┬──────────────┘
                           │
       ┌───────────────────┴───────────────────┐
       ▼ (Direct Upload)                       ▼ (Enqueue task metadata)
┌──────────────┐                       ┌───────────────┐
│  Amazon S3   │                       │ Redis Cluster │ (Celery Broker with Sharding)
└──────┬───────┘                       └───────┬───────┘
       │                                       ▼
       │                               ┌───────────────┐
       │                               │ Celery Workers│ (Auto-scaled using KEDA on
       │                               └───────┬───────┘  Kubernetes queue depth)
       │ (Fetch file)                          │
       └───────────────────┬───────────────────┘
                           ▼
                   ┌───────────────┐
                   │  Postgres DB  │ (Aurora Serverless with Read Replicas &
                   └───────────────┘  PgBouncer connection pooler)
```

1. **Object Storage for Uploads**:
   - FastAPI should generate S3 Pre-signed URLs for clients to upload CSVs directly to **Amazon S3** or **MinIO**. FastAPI and Celery only pass the metadata S3 URI, saving server disk and network bandwidth.
2. **Kubernetes Deployment (EKS/GKE)**:
   - Run FastAPI and Celery workers on Kubernetes.
   - Use **KEDA (Kubernetes Event-driven Autoscaling)** to scale Celery worker pods based on queue depth (e.g. number of pending messages in Redis).
3. **Database Scaling**:
   - Implement **PgBouncer** or **AWS RDS Proxy** to manage and pool open connections.
   - Deploy **Read Replicas** for transaction read routes (`/results` and `/status`), leaving the writer node dedicated to ingestion.
   - Use **SQLAlchemy bulk save mappings** (`db.bulk_insert_mappings`) or `COPY FROM` buffer streams for PostgreSQL block insertion instead of model ORM instantiations.
4. **Queue Clustering**:
   - Replace standalone Redis with **Redis Cluster** or a distributed message broker like **Apache Kafka** / **RabbitMQ** to achieve broker fault tolerance.
5. **LLM Rate-Limit Mitigation**:
   - Implement an enterprise LLM gateway with token bucket rate limiting.
   - Use an asynchronous job worker pattern that chunks classification batches (e.g. 50 transactions per prompt) and handles 429 retries using a dead-letter queue (DLQ).
6. **Observability Stack**:
   - Integrate **Prometheus** and **Grafana** for queue size monitoring.
   - Use **OpenTelemetry** + **Jaeger** / **Datadog** for tracing requests and identifying API rate bottlenecks.
