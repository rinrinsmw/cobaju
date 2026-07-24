# Cobaju Demo Preflight

Run these checks from the repository root. Start Redis, FastAPI, the Celery
worker, and the frontend in separate terminals before completing the end-to-end
checks. Never paste real credentials into this document or commit them.

## 1. Configuration

Confirm that the local environment file exists and that the variables needed by
the demo have values:

```bash
test -f .env
for variable in JWT_SECRET_KEY DATABASE_URL REDIS_URL OPENROUTER_API_KEY OPENROUTER_GUARDRAIL_MODEL OPENROUTER_VISION_MODEL OPENROUTER_EMBEDDING_MODEL OPENROUTER_CHAT_GUARDRAIL_MODEL OPENROUTER_STYLIST_MODEL OPENROUTER_STYLE_CRITIC_MODEL; do
  grep -Eq "^${variable}=.+$" .env || echo "Missing: ${variable}"
done
```

Make sure secrets and model names are not still using the example placeholders:

```bash
if grep -Eq '^(JWT_SECRET_KEY|OPENROUTER_API_KEY|OPENROUTER_.*_MODEL)=replace-with-' .env; then
  echo "Replace the remaining example values before the demo."
else
  echo "Core AI configuration is present."
fi
```

If Langfuse is enabled, confirm its three settings are present:

```bash
if grep -Eq '^LANGFUSE_ENABLED=true$' .env; then
  for variable in LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_HOST; do
    grep -Eq "^${variable}=.+$" .env || echo "Missing: ${variable}"
  done
else
  echo "Langfuse is disabled; telemetry will use the no-op backend."
fi
```

## 2. Infrastructure and applications

Apply the existing migrations:

```bash
moon run backend:migrate
```

Start Redis if it is not already running, then verify it:

```bash
redis-server
```

```bash
redis-cli ping
```

The expected Redis response is `PONG`.

Start the API and worker in separate terminals:

```bash
moon run backend:dev
```

```bash
moon run backend:worker
```

From another terminal, verify the worker, API, and database:

```bash
uv run --project apps/backend celery --workdir apps/backend -A app.celery_app:celery_app inspect ping
curl --fail --silent --show-error http://127.0.0.1:8000/health
curl --fail --silent --show-error http://127.0.0.1:8000/health/database
```

Start and verify the frontend:

```bash
moon run frontend:dev
```

```bash
curl --fail --silent --show-error --output /dev/null http://127.0.0.1:8443
echo "Frontend is available."
```

## 3. Demo account and main journey

Enter the demo credentials without saving them in shell history, then verify
login and keep the short-lived token only in the current terminal:

```bash
read -r -p "Demo email: " DEMO_EMAIL
read -r -s -p "Demo password: " DEMO_PASSWORD
echo
DEMO_TOKEN=$(curl --fail --silent --show-error -X POST http://127.0.0.1:8000/auth/login -H 'Content-Type: application/json' --data "{\"email\":\"${DEMO_EMAIL}\",\"password\":\"${DEMO_PASSWORD}\"}" | uv run --project apps/backend python -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')
test -n "${DEMO_TOKEN}" && echo "Test login succeeded."
```

Confirm the account has at least one confirmed wardrobe item:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/wardrobe/items -H "Authorization: Bearer ${DEMO_TOKEN}" | uv run --project apps/backend python -c 'import json, sys; items=json.load(sys.stdin); confirmed=[item for item in items if item["processing_status"] == "completed"]; print(f"Confirmed wardrobe items: {len(confirmed)}"); raise SystemExit(0 if confirmed else 1)'
```

Run one Stylist request and verify that it returns a recommendation with a
Lookbook save receipt:

```bash
DEMO_CHAT_RESPONSE=$(curl --fail --silent --show-error -X POST http://127.0.0.1:8000/chat/recommendations -H "Authorization: Bearer ${DEMO_TOKEN}" -H 'Content-Type: application/json' --data '{"message":"Create a smart-casual demo outfit using my wardrobe."}')
printf '%s' "${DEMO_CHAT_RESPONSE}" | uv run --project apps/backend python -c 'import json, sys; response=json.load(sys.stdin); print("Stylist status: {}".format(response["status"])); raise SystemExit(0 if response["status"] == "recommendation" and response.get("lookbook_save_token") else 1)'
```

Save that recommendation to the Lookbook and confirm the save succeeds:

```bash
DEMO_SAVE_TOKEN=$(printf '%s' "${DEMO_CHAT_RESPONSE}" | uv run --project apps/backend python -c 'import json, sys; print(json.load(sys.stdin)["lookbook_save_token"])')
curl --fail --silent --show-error -X POST http://127.0.0.1:8000/recommendations -H "Authorization: Bearer ${DEMO_TOKEN}" -H 'Content-Type: application/json' --data "{\"save_token\":\"${DEMO_SAVE_TOKEN}\",\"display_title\":\"Demo Preflight\"}"
```

Clear the temporary shell values when finished:

```bash
unset DEMO_EMAIL DEMO_PASSWORD DEMO_TOKEN DEMO_CHAT_RESPONSE DEMO_SAVE_TOKEN
```

Finally, open <http://127.0.0.1:8443> and visually confirm Login, Wardrobe,
Stylist, and the newly saved Lookbook entry before presenting.
