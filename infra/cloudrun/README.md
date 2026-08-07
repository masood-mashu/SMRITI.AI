# Cloud Run deployment

These manifests are deployment templates, not live credentials. Replace the
PROJECT, REGION, TAG, service account, secret names, and API host before
applying them.

Deploy migrations separately before shifting traffic:

gcloud run services replace infra/cloudrun/api-service.yaml
gcloud run services replace infra/cloudrun/frontend-service.yaml

The API template assumes PostgreSQL, Redis, OIDC, and Secret Manager are
already provisioned. It also expects Vertex AI, GCS, and Cloud KMS permissions
on the runtime service account. Replace the `PROJECT`, `REGION`, image tags,
service account, and secret names before applying. Do not place database URLs,
signing keys, or API tokens directly in these YAML files.

The API manifest intentionally binds to Cloud Run's `8080` container port and
uses `/health/live` for startup/liveness checks. The frontend uses the same
injected `PORT` through a shell command so it remains compatible with Cloud
Run's runtime contract.

Before deployment, provision these Secret Manager entries:

- `smriti-database-url`
- `smriti-redis-url`
- `smriti-oidc-issuer`
- `smriti-oidc-audience`
- `smriti-gcs-bucket`
- `smriti-gcs-kms-key`
- `smriti-api-token` for the frontend
- `smriti-ingestion-worker-token` for authenticated Cloud Tasks callbacks

Create the ingestion queue and deploy the worker-capable API before enabling
production uploads:

```powershell
gcloud tasks queues create smriti-ingestion --location=REGION
gcloud run jobs replace infra/cloudrun/storage-cleanup-job.yaml
gcloud scheduler jobs create http smriti-storage-cleanup --schedule="0 3 * * *" `
  --uri="https://run.googleapis.com/apis/run.googleapis.com/v1/projects/PROJECT/locations/REGION/jobs/smriti-storage-cleanup:run" `
  --http-method=POST --oauth-service-account-email=SMRITI_SCHEDULER_SERVICE_ACCOUNT
```

For GCS-backed production storage, apply the bucket lifecycle policy in
`infra/gcs/lifecycle.json` instead of relying on the local cleanup job.
