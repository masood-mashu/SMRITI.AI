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
