bind = 'unix:/tmp/2salti.sock'
workers = 3

# Worker timeout raised from the 30s default: the report upload view calls the
# Gemini OCR synchronously inside the request cycle (~80s per report, measured
# live on 2026-07-10). At 30s the gunicorn master aborted the worker mid-call
# (500 to the client, report stuck in PROCESSING). Provisional value until OCR
# processing goes async (dedicated macro).
timeout = 300

# Logging (added 2026-04-23 — problema #3 della session note)
errorlog = '/var/log/2salti/error.log'
accesslog = '/var/log/2salti/access.log'
capture_output = True
loglevel = 'info'
