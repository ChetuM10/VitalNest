# T0 — AWS skeleton: what was built and how to deploy it

Nothing has been deployed. No AWS resources exist yet. This file explains the configuration and the steps you run after approving.

## What T0 contains

| File | Purpose |
|---|---|
| `backend/app/main.py` | App factory: CORS, shared error shape, router registration |
| `backend/app/api/health.py` | `GET /v1/health`, public |
| `backend/app/api/identity.py` | Reads the Cognito claims that API Gateway forwards (T0 only; T1b replaces it with real JWT verification in FastAPI) |
| `backend/app/api/me.py` | `GET /v1/me`, protected, returns `sub` and `email` |
| `backend/app/api/stream_spike.py` | `GET /v1/stream-spike`, protected, timed SSE events; removed once `/v1/chat` exists (T11) |
| `backend/run.sh` | Starts uvicorn; the Lambda Web Adapter runs this |
| `infra/template.yaml` | SAM template: Cognito, REST API, Lambda, throttling |
| `backend/tests/unit/test_t0_skeleton.py` | 12 tests |

## What the template creates (billable-resource review)

| Resource | Cost at prototype scale |
|---|---|
| Cognito user pool, app client, Hosted UI domain | Free tier covers 50,000 monthly users |
| API Gateway REST API (throttled 5 rps, burst 10) | Per request; negligible |
| Lambda (512 MB, x86_64) + Web Adapter layer | Free tier covers the prototype |
| IAM role (created by SAM), CloudWatch log group | Log storage only; negligible |

No Secrets Manager, Pinecone, Claude or Budget resources yet. Those come with later tasks.

## Prerequisites (not installed on this machine)

1. AWS CLI, configured with credentials for the target account (`aws configure`).
2. AWS SAM CLI.
3. Docker is **not expected to be needed**: SAM downloads Linux wheels for the Lambda runtime. If `sam build` reports a native build problem, use `sam build --use-container` (requires Docker Desktop).
4. A globally unique Cognito domain prefix, e.g. `vitalnest-<yourname>-<digits>`.
5. The template defaults to Lambda Web Adapter layer version 30, the version used in the adapter's official FastAPI streaming example. The deploy checks it exists in your region.
6. The Cognito domain prefix must be lowercase letters, digits and hyphens, and must not contain `aws`, `amazon` or `cognito`.

## Deployment steps (after you approve)

```bash
cd infra
sam validate --lint
sam build
sam deploy --guided --parameter-overrides CognitoDomainPrefix=<your-prefix>
```

`--guided` asks for the stack name (`vitalnest-t0`) and region, and confirms IAM role creation. Review the changeset before accepting. Note the stack outputs (`ApiUrl`, `UserPoolId`, `UserPoolClientId`, `HostedUiBaseUrl`).

## Verification steps (acceptance for T0)

1. Public health, no token:
   ```bash
   curl <ApiUrl>/v1/health
   ```
   Expect `{"status":"ok","version":"0.0.1"}`.
2. Protected route without a token must be rejected by the gateway:
   ```bash
   curl -i <ApiUrl>/v1/me
   ```
   Expect `401`.
3. Create a user: open
   `<HostedUiBaseUrl>/login?client_id=<UserPoolClientId>&response_type=code&scope=openid+email&redirect_uri=http://localhost:5173/callback`,
   choose Sign up, confirm the emailed code. The browser redirects to a page that fails to load; copy the `code` value from the address bar.
4. Exchange the code for tokens:
   ```bash
   curl -X POST <HostedUiBaseUrl>/oauth2/token \
     -d grant_type=authorization_code -d client_id=<UserPoolClientId> \
     -d code=<code> -d redirect_uri=http://localhost:5173/callback
   ```
5. Protected route with the `id_token` from step 4:
   ```bash
   curl -H "Authorization: Bearer <id_token>" <ApiUrl>/v1/me
   ```
   Expect your `sub` and `email`.
6. **Streaming spike.** `-N` disables curl's buffering:
   ```bash
   curl -N -H "Authorization: Bearer <id_token>" "<ApiUrl>/v1/stream-spike?count=5&delay_ms=1000"
   ```
   **Pass:** the five `token` events appear about one second apart, then `done`.
   **Fail:** everything arrives at once after about 5 seconds, meaning the response was buffered.
7. Browser CORS check (from the Vercel or localhost origin): `fetch` the stream with the `Authorization` header and read `response.body.getReader()`.

## Streaming spike: what it decides

| Result | Action |
|---|---|
| Events arrive incrementally | Plan confirmed: REST API + Web Adapter |
| Deployment rejects the integration, or events are buffered | Switch to the documented fallback: Lambda Function URL with response streaming, FastAPI verifying the JWT (T1b brings that forward) |
| Neither works | Non-streaming responses |

## Known unverified items (cannot be checked without deploying)

- The `responseTransferMode: STREAM` setting and the `/response-streaming-invocations` integration URI in `infra/template.yaml` follow API Gateway's REST streaming feature. `cfn-lint` accepts the template, but only a real deploy confirms API Gateway honours them.
- Whether the Web Adapter forwards the authorizer claims in `x-amzn-request-context` when the gateway uses the streaming invocation path.
- Whether the gateway's Cognito authorizer accepts `Authorization: Bearer <id_token>`. Sources disagree. If step 5 returns 401 with a fresh token, retry with the raw token (no `Bearer `). If only the raw token works, the gateway authorizer is dropped in favour of FastAPI-side verification (T1b), which the plan already requires.
- Lambda log groups are created on first invocation with no expiry. They cost almost nothing, but `sam delete` does not remove them.
- Cold start and package size are measured later (T17).

## Security notes for T0

- The `/v1/me` identity comes from a header the Web Adapter fills from the gateway event. The function has no public URL, so only API Gateway can invoke it. This is **not** a substitute for T1b, where FastAPI verifies the token itself as the plan requires.
- CORS allows only the `AllowedOrigin` parameter value. Update it to the Vercel URL on redeploy.
- Gateway 401/403 responses carry CORS headers, so browsers show the real error.
