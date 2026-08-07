# GCS retention lifecycle

Apply this policy to the production report bucket after replacing the bucket
name and confirming the retention period with the service owner:

```powershell
gsutil lifecycle set infra/gcs/lifecycle.json gs://YOUR_REPORT_BUCKET
gsutil lifecycle get gs://YOUR_REPORT_BUCKET
```

The application deletion endpoint remains responsible for patient-requested
deletion. This lifecycle policy is the scheduled expiry backstop and should be
paired with the bucket's required CMEK configuration.
