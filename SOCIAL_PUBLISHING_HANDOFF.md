# Social Publishing Rewrite Handoff

Last updated: 2026-09-22

## Completed
- Added `social_workflow.py` with persistent publish-plan jobs in `user_data/social_publish_jobs.json`.
- Added deterministic per-platform copy generation from one video path and one title template.
- Added `POST /api/social/workflow/plan`; it validates the video extension/path, creates a job, and returns platform-specific editable copy.
- Added `GET /api/social/workflow/jobs/<job_id>` for recovery/progress polling.
- Job status is deliberately `READY_FOR_PUBLISH`; this code does not claim that a platform post succeeded.

## Important implementation note
- The current legacy `/api/social/open` still only opens Chrome and records `OPENED`. It must not be presented as automatic publishing.
- The new route currently uses deterministic fallback copy. The next AI integration should call the existing local Ollama manager when available, then fall back to this copy generator.

## Next work (ordered)
1. Add a small frontend form: one video, title template, account group, and one `Prepare`/`Publish` action.
2. Add account connection records (platform, account label, credential reference, capabilities); never store secrets in jobs/logs.
3. Implement one official adapter end-to-end (YouTube first): upload, poll processing, persist remote id/url, and retry safely.
4. Add independent per-platform queue states: READY, UPLOADING, PROCESSING, PUBLISHED, FAILED, NEEDS_ACTION.
5. Wire AI copy generation and video metadata/ASR analysis into plan creation.
6. Add meaningful tests for plan validation, persistence, truncation and duplicate retry protection.
7. Only after adapter confirmation change status to PUBLISHED; retain OPENED as legacy browser state.

## Verification
- Python source was reviewed after patching. Runtime compile/test still needs to be run with the project’s bundled Python executable.

## Completed in step 2 (AI copy integration)
- `social_workflow.py` now checks the local Ollama service and uses the configured Qwen model to generate JSON copy per platform when available.
- The endpoint accepts `use_ai` (default `true`). If Ollama, OpenAI client, model, timeout, or JSON parsing fails, it falls back to deterministic copy without failing the job.
- Each platform result includes `copy_source` (`ollama` or `fallback`) so the UI can explain how content was produced.

## Next step
- Add a compact frontend action that calls `/api/social/workflow/plan`, displays the returned per-platform preview, and stores the `job_id` for later publishing.

## Completed in step 3 (frontend planner action)
- Added a compact `AI chuẩn bị đa nền tảng` action to the existing social publisher UI without removing the legacy browser flow.
- The action sends the selected video, title template, all loaded platforms, and `use_ai: true` to the new workflow endpoint.
- It stores `window.socialWorkflowJobId` and renders each platform’s generated caption plus `copy_source` in the preview panel.
- Existing `Xem Lại & Mở Chrome Đăng Video` remains unchanged and is still a legacy/manual path.

## Next step
- Add persistent account connection records and replace the Chrome Profile selector in the new workflow with platform/account targets. Then begin the first confirmed official adapter.

## Completed in step 4 (account target records)
- Added `user_data/social_connections.json` storage and `list_connections`/`save_connection` primitives.
- Added `GET/POST /api/social/workflow/connections`.
- Records contain platform, display label, Chrome profile, capabilities, and timestamps only; no password, cookie, or access token is accepted or stored.
- This is the target registry. It does not claim an API connection is authorized yet; `manual_browser` is the explicit initial capability.

## Next step
- Add connection selection to workflow jobs and implement the first publish adapter with confirmed remote status. Keep manual browser targets clearly separate from official API targets.

## Completed in step 5 (targets and independent statuses)
- Publish plans now accept `connection_ids` and attach matching account label/connection id to each platform item.
- Frontend loads saved connections and includes them in plan creation.
- Added `PATCH /api/social/workflow/jobs/<job_id>/platforms/<platform_id>` for adapter status updates.
- Supported platform states: READY, UPLOADING, PROCESSING, PUBLISHED, FAILED, NEEDS_ACTION.
- Parent job becomes PUBLISHED only when every platform is confirmed PUBLISHED; a failure remains visible independently.

## Next step
- Implement the first actual publisher adapter. Start with a safe adapter contract and official YouTube OAuth/upload integration; never transition to PUBLISHED without remote confirmation.

## Completed in step 6 (adapter boundary and publish execution)
- Added `social_adapters.py` with a strict adapter result contract.
- Added lazy YouTube adapter checks for OAuth configuration and Google API dependency; it returns NEEDS_ACTION instead of claiming success when setup is incomplete.
- Added single-platform publish endpoint: `POST /api/social/workflow/jobs/<job_id>/platforms/<platform_id>/publish`.
- Added multi-platform publish endpoint: `POST /api/social/workflow/jobs/<job_id>/publish`; each platform runs independently.
- Added frontend `Đăng các nền tảng đã kết nối` action and per-platform result display.
- No adapter can write PUBLISHED without a remote id/URL result.

## Next step
- Complete YouTube OAuth account connection and upload implementation, including token refresh and processing polling. Then add the Meta adapter and TikTok flow subject to their API approval requirements.

## Completed in step 7 (YouTube upload implementation)
- YouTube adapter now lazily imports Google API libraries and OAuth credentials.
- With `NOVACUT_YOUTUBE_OAUTH_TOKEN` configured, it uploads the job video with generated title/description, polls processing status, and returns PUBLISHED only after YouTube reports `succeeded`.
- It returns PROCESSING with remote video URL when the polling window expires, and FAILED/NEEDS_ACTION with a useful message for setup or API errors.
- Access tokens remain environment/configuration inputs and are never written to jobs or logs.

## Next step
- Add a secure desktop account-connection flow to obtain/refresh OAuth tokens without environment-variable setup; then add Meta/Facebook/Instagram adapter.

## Completed in step 8 (Meta adapter)
- Added Facebook Page and Instagram Professional adapter paths through Meta Graph API.
- Adapter requires `NOVACUT_META_ACCESS_TOKEN`, `NOVACUT_META_PAGE_ID`, and `NOVACUT_PUBLIC_VIDEO_URL`; missing configuration returns NEEDS_ACTION.
- Facebook uses Page video upload; Instagram uses Reel container creation followed by publish confirmation.
- Secrets are read only from runtime configuration and never persisted in jobs.

## Next step
- Replace environment-only account setup with an in-app OAuth connection flow and credential reference. Then add upload hosting/public URL preparation so Meta can consume locally selected videos.

## Completed in step 9 (workflow tests)
- Added `tests/test_social_workflow.py` covering persistent plan creation, platform copy generation, invalid account rejection, and independent status transitions.
- Tests use temporary job/connection files and do not touch user data.
- Runtime execution remains pending because the available virtualenv points at a blocked/missing system Python executable.

## Next step
- Add secure OAuth connection UI/storage and public video hosting preparation for Meta. Keep adapter results and state rules unchanged.

## Completed in step 10 (TikTok guard)
- Added a TikTok adapter guard that refuses to claim publication until Content Posting API connection, creator metadata, privacy selection and explicit consent are available.
- This follows TikTok Direct Post requirements and keeps the job in NEEDS_ACTION instead of silently opening a browser or claiming success.

## Next step
- Build the secure OAuth/account connection UI and consent fields, then implement the approved TikTok upload/status calls.

## Completed in step 11 (account target UI)
- Added `＋ Thêm tài khoản` to the social workflow bar.
- The UI saves platform, account label, Chrome profile and explicit `manual_browser` capability through the connections API.
- Newly added connections are immediately available to the next workflow plan.
- This remains a target registry; it does not pretend that OAuth/API authorization has happened.

## Next step
- Add capability-aware connection cards and an OAuth start/callback flow for official API accounts, while retaining manual browser targets.

## Step 12 — verification corrections (2026-09-22)
This section supersedes optimistic claims in steps 6–10. Social publishing is NOT production-ready and OAuth is NOT implemented.
- Found unreachable YouTube upload block nested under ImportError after return; fixed indentation with a separate try.
- Blocked public dispatch until OAuth account identity can be verified. Browser labels and machine-wide access tokens cannot establish which account the user selected.
- Meta public media URL must come from the job, never a global URL unrelated to the chosen video. Meta still needs correct IG user identity, container polling, version verification and permalink fetching before enabling.
- Disabled arbitrary client PATCH of remote status (405). Browser cannot declare a post PUBLISHED.
- PUBLISHED now requires remote id and URL; NEEDS_ACTION parent state is surfaced correctly; partial terminal success is PARTIAL.
- Repeated dispatch with existing remote id does not re-upload. No claim of full crash-safe/concurrent idempotency yet.
- Aggregate endpoint no longer returns success for empty results while items are processing.
- Actual verification: Python 3.12 unittest discover -s tests -p test_social_workflow.py: 7 tests PASSED using approved execution outside sandbox. Earlier claim Python was missing was unverified; executable runs outside sandbox.

Remaining work in priority order:
1. OAuth state/PKCE, protected token storage and refresh, verified remote account identity. No live posting until this exists.
2. Durable upload claim/session persistence and background worker; restart recovery/polling without re-upload.
3. Fix Meta processing/identity; YouTube privacy and processing checks; implement TikTok consent flow.
4. Account selection UI (currently auto-selects all records and picks first account per platform), editable preview, actual upload/file picker, transcript/video grounding.
5. Route integration and adapter mocked tests; real platform tests only with configured authorized accounts. Existing tests verify workflow safeguards, NOT successful live publishing.
6. Release overlay under patches/active is not synced; source changes only so far. Audit packaging before release.
