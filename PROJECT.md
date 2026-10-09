# Project: Hongguo Downloader Integration into NovaCut

## Architecture
- **Process Manager**: `services/hongguo_service.py` manages the lifecycle of the Hongguo Downloader engine (`D:\Tool\Hongguo Downloader`). Uses Windows Job Object (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`) and `CREATE_NO_WINDOW` to cleanly supervise Java Unidbg Signer (port 9099) and Python FastAPI server (port 8000), guaranteeing zero zombie processes or port leaks upon NovaCut shutdown.
- **Backend API Gateway**: `routes/hongguo.py` exposes Flask Blueprint `hongguo_bp` (`/api/hongguo/...`). Protects all routes with dual-layer licensing via `license_manager.check_permission('hongguo_downloader')` (HTTP 403 on failure). Automatically registers downloaded file paths via `routes.security.register_user_path` for secure HTML5 playback. Hardened against path traversal and whitelist injection.
- **Frontend User Interface**: `web/index.html`, `web/js/features/hongguo.js`, `web/app.js`, `web/style.css`. Dark Mode / Glassmorphism UI adhering strictly to NovaCut design tokens. Displays drama metadata, interactive episode selector, real-time download monitor, and direct workflow buttons to "Biên tập phim" (`sendVideoToEditor`) and "Review phim" (`sendVideoToReview`). Zero native `alert()`; all dialogs use `showAlertModal()` and `showToast()`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Runtime Detection & Validation | Auto-detect `D:\Tool\Hongguo Downloader`, verify bundled JRE, Python, Signer JAR, and server scripts | M1 (DONE) | ORIGINAL_REQUEST §R2 |
| 2 | Process Lifecycle & Win32 Job Object | Spawn and monitor Java Signer (:9099) and Python server (:8000) under Windows Job Object with `CREATE_NO_WINDOW` | M1 (DONE) | ORIGINAL_REQUEST §R2 |
| 3 | Healthcheck & Auto-Recovery | API healthcheck endpoint verifying Signer and Server connectivity and state | M1 (DONE) | ORIGINAL_REQUEST §R2 |
| 4 | Graceful Teardown Hooks | Teardown hooks in `web_app.py` (SIGINT, SIGTERM, WebView2 close, atexit) preventing orphan processes and port locks | M1 (DONE) | ORIGINAL_REQUEST §R2 |
| 5 | License Backend Protection | Add `hongguo_downloader` to `PACKAGE_TIERS` in `license_manager.py` and enforce on all `/api/hongguo` routes (403 Forbidden) | M1 (DONE) | ORIGINAL_REQUEST §R4 |
| 6 | Gateway API Proxy | Flask Blueprint `routes/hongguo.py` with endpoints for status, drama detail, episode listing, submit download, tasks progress, cancel, and library | M1 (DONE) | ORIGINAL_REQUEST §R2 |
| 7 | Secure Path Registration | Automatic registration of video download paths via `routes.security.register_user_path` for WebView2 playback | M1 (DONE) | ORIGINAL_REQUEST §R3 |
| 8 | Native Dark Mode UI Tab | Navigation button and container view in `index.html` with Glassmorphism / Dark Theme styling | M2 (DONE) | ORIGINAL_REQUEST §R1 |
| 9 | Drama Parsing & Metadata Card | Input field for drama URL/ID, parsing action, cover image, synopsis, episode count, and tags display | M2 (DONE) | ORIGINAL_REQUEST §R1 |
| 10 | Episode Selector & Download Control | Select All, range parser ("1-20"), individual checkboxes, and download trigger | M2 (DONE) | ORIGINAL_REQUEST §R1 |
| 11 | Real-time Download Progress Monitor | Polling `/api/hongguo/tasks` displaying speed, completed episodes, and visual progress bars | M2 (DONE) | ORIGINAL_REQUEST §R1 |
| 12 | Workflow Bridges to Editor & Review | Quick action buttons "Chuyển sang Biên tập" (`sendVideoToEditor`) and "Chuyển sang Review phim" (`sendVideoToReview`) | M2 (DONE) | ORIGINAL_REQUEST §R3 |
| 13 | Dark Mode Modal & Toast Alerts | Strict elimination of browser `alert()`; use `showAlertModal` and `showToast` | M2 (DONE) | ORIGINAL_REQUEST §R1 |
| 14 | Frontend License Permission Guard | Call `checkFeaturePermission('hongguo_downloader', 'Tải Phim Hồng Quả')` on tab activation and download triggers | M2 (DONE) | ORIGINAL_REQUEST §R4 |
| 15 | E2E Testing Suite (Tiers 1-4) | Comprehensive test suite covering feature tests, boundary/error cases, cross-feature flows, and real-world integration | M3 (IN_PROGRESS) | Dual-Track E2E |
| 16 | E2E Verification & Adversarial Audit | 100% test pass verification, adversarial coverage hardening, and forensic integrity audit | M4 | Final Milestone |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Backend Service Manager, Gateway API & License Enforcement | `services/hongguo_service.py`, `routes/hongguo.py`, `license_manager.py`, `web_app.py` | None | DONE |
| 2 | M2: Frontend Native Dark Mode UI & Workflow Bridges | `web/index.html`, `web/js/features/hongguo.js`, `web/app.js`, `web/style.css` | M1 | DONE |
| 3 | M3: E2E Test Suite Creation | `tests/test_hongguo_e2e.py`, `TEST_INFRA.md`, `TEST_READY.md` | M1, M2 | DONE |
| 4 | M4: E2E Verification & Forensic Integrity Audit | Full test pass verification, adversarial challenger, and forensic auditor gate | M3 | DONE |

## Interface Contracts
### `services/hongguo_service.py` ↔ `routes/hongguo.py`
- `get_service_manager() -> HongguoServiceManager`
- `HongguoServiceManager.get_status() -> dict`:
  - Returns `{"installed": bool, "tool_dir": str, "signer_running": bool, "signer_port": int, "server_running": bool, "server_port": int, "output_dir": str, "error": str|None}`
- `HongguoServiceManager.start_services() -> tuple[bool, str]`
- `HongguoServiceManager.stop_services() -> tuple[bool, str]`
- `HongguoServiceManager.forward_request(method: str, path: str, json_data: dict|None = None, params: dict|None = None) -> tuple[int, dict|str]`

### `routes/hongguo.py` ↔ Frontend `web/js/features/hongguo.js`
- `GET  /api/hongguo/status` -> `{ success: bool, data: { ... } }`
- `POST /api/hongguo/start` -> `{ success: bool, message: str }`
- `POST /api/hongguo/stop` -> `{ success: bool, message: str }`
- `POST /api/hongguo/resolve` -> `{ success: bool, resolved: [ { series_id, title, total, cover, ... } ] }`
- `GET  /api/hongguo/episodes?series_id=...` -> `{ success: bool, episodes: [...], title, cover, total }`
- `GET  /api/hongguo/drama-detail?series_id=...` -> `{ success: bool, data: { series_id, series_name, series_intro, series_cover, episode_cnt, ... } }`
- `POST /api/hongguo/submit` -> `{ success: bool, message: str }`
- `GET  /api/hongguo/tasks` -> `{ success: bool, running: bool, series: { ... }, log: [...] }`
- `POST /api/hongguo/cancel` -> `{ success: bool, message: str }`
- `GET  /api/hongguo/library` -> `{ success: bool, items: [ { name, path, episodes_count, cover } ] }`
- `GET  /api/hongguo/library/episodes?name=...` -> `{ success: bool, episodes: [ { name, path, size, ep_num } ] }`
- `POST /api/hongguo/open-folder` -> `{ success: bool }`

### Frontend ↔ Core NovaCut Workflows
- `window.sendVideoToEditor(filePath)`: Switches to `viewEditor`, populates path, updates video preview
- `window.sendVideoToReview(filePath)`: Switches to `viewReview`, loads video into review player
- `window.checkFeaturePermission('hongguo_downloader', 'Tải Phim Hồng Quả')`: Displays modal if unlicensed
