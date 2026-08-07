# Cloud Run deployment

These manifests are deployment templates, not live credentials. Replace the
PROJECT, REGION, TAG, service account, secret names, and API host before
applying them.

Deploy migrations separately before shifting traffic:

gcloud run services replace infra/cloudrun/api-service.yaml
gcloud run services replace infra/cloudrun/frontend-service.yaml

The API template assumes PostgreSQL, Redis, OIDC, and Secret Manager are
already provisioned. Do not place database URLs, signing keys, or API tokens
directly in these YAML files.
