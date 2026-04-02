#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-daily-health-agent}"

: "${FITBIT_CLIENT_ID:?Set FITBIT_CLIENT_ID}"
: "${FITBIT_CLIENT_SECRET:?Set FITBIT_CLIENT_SECRET}"
: "${FITBIT_REFRESH_TOKEN:?Set FITBIT_REFRESH_TOKEN}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY}"
: "${CLAUDE_API_KEY:?Set CLAUDE_API_KEY}"
: "${LINE_CHANNEL_ACCESS_TOKEN:?Set LINE_CHANNEL_ACCESS_TOKEN}"
: "${DB_PASSWORD:?Set DB_PASSWORD}"
: "${DRIVE_ROOT_FOLDER_ID:?Set DRIVE_ROOT_FOLDER_ID}"

printf '%s' "${FITBIT_CLIENT_ID}" | gcloud secrets versions add fitbit-client-id \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${FITBIT_CLIENT_SECRET}" | gcloud secrets versions add fitbit-client-secret \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${FITBIT_REFRESH_TOKEN}" | gcloud secrets versions add fitbit-refresh-token \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${OPENAI_API_KEY}" | gcloud secrets versions add openai-api-key \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${CLAUDE_API_KEY}" | gcloud secrets versions add claude-api-key \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${LINE_CHANNEL_ACCESS_TOKEN}" | gcloud secrets versions add line-channel-access-token \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${DB_PASSWORD}" | gcloud secrets versions add db-password \
  --data-file=- --project "${PROJECT_ID}"
printf '%s' "${DRIVE_ROOT_FOLDER_ID}" | gcloud secrets versions add drive-root-folder-id \
  --data-file=- --project "${PROJECT_ID}"

echo "Secret versions updated in project ${PROJECT_ID}."
