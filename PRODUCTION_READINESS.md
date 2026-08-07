# Smriti AI Production Readiness

This document is the operational gate for deploying Smriti with real patient data.

## Pre-deployment gates

- `SMRITI_ENV=production` and `SMRITI_VALIDATE_PRODUCTION=true`.
- OIDC is configured with issuer, audience, JWKS validation, and patient binding.
- PostgreSQL migrations have been applied; `DB_AUTO_CREATE=false`.
- Redis is configured for rate limiting.
- GCS is configured with a KMS key; local unencrypted storage is not a production option.
- `PHI_STRICT=true` and upload signature checks are enabled.
- Synthetic-data tests, static security scan, dependency audit, lint, and the full test suite pass.
- A qualified reviewer has approved the extraction and generated-output evaluation set.

## Deployment and rollback

1. Build an immutable container image from the reviewed commit.
2. Apply migrations before shifting traffic.
3. Deploy a new Cloud Run revision with no traffic, run health and smoke checks, then shift traffic gradually.
4. Monitor 5xx rate, latency, provider failures, authentication failures, database pool saturation, and ingestion success.
5. Roll back traffic to the previous revision if error rate or privacy/security alarms breach the release threshold.
6. Treat destructive database migrations as separate, reviewed releases; do not rely on automatic downgrades for data recovery.

## Incident response

- Authentication or cross-patient access alert: disable traffic, preserve audit logs, rotate credentials, identify affected patients, and follow the breach-notification process.
- Provider or model incident: disable the affected provider through configuration and use the deterministic safe fallback where clinically appropriate.
- Storage incident: disable uploads, preserve object/audit identifiers, rotate KMS or service credentials, and verify retention/deletion jobs.
- Every incident requires a timeline, impact assessment, containment, remediation, and post-incident review.

## Clinical safety boundary

Smriti extracts and summarizes recorded facts. It must not autonomously diagnose, prescribe, or replace clinician review. Generated output requires grounding to stored facts, visible uncertainty, and human review before clinical action.

HIPAA/GDPR legal review, BAAs/data-processing agreements, penetration testing, and formal clinical validation remain organizational gates outside code-only verification.
