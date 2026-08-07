# Synthetic AI evaluation

The evaluation cases in this directory are synthetic and contain no patient data.
They provide a deterministic regression baseline for the extraction contract; they
do not prove clinical accuracy or replace a labeled medical evaluation set.

Run locally with:

```powershell
.\.venv\Scripts\python.exe scripts/run_extraction_eval.py
```

The command exits non-zero if the expected fact keys are not produced. A future
provider evaluation can reuse the same cases and report precision, recall, and
field-level validation against a reviewed, de-identified dataset.
