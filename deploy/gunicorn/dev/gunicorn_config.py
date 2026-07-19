bind = 'unix:/tmp/2salti-dev.sock'
workers = 2

# Worker timeout raised from the 30s default — same rationale as prod (see
# prod/gunicorn_config.py): synchronous Gemini OCR takes ~80s per report.
# Provisional value until OCR processing goes async.
timeout = 300

# Dev: log via stderr -> journalctl -u 2salti-dev.service
capture_output = True
loglevel = 'info'
