# Test Infrastructure & Strategy: Hongguo Downloader E2E Integration

## 1. Test Philosophy

The Hongguo Downloader end-to-end test suite for NovaCut adheres to the following foundational engineering principles:

1. **Opaque-Box & Requirement-Driven**: Tests treat components as black/opaque boxes adhering to strict public interface contracts defined in `PROJECT.md` and `ORIGINAL_REQUEST.md` (R1–R4). Tests exercise genuine HTTP endpoints, service lifecycle methods, license checks, and DOM/workflow bridge hooks rather than inspecting private implementation trivia.
2. **Deterministic & Isolated Execution**: Every test sets up its own isolated state, utilizes temporary sandboxed directories or clean mocks for volatile external network requests, and leaves zero orphan processes or filesystem pollution.
3. **Defense-in-Depth & Security-First**: Dual-layer license protection (frontend guard + backend HTTP 403 enforcement), path traversal prevention (`safe_join`, `_is_within`), and Win32 Job Object process boundary controls (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`, `CREATE_NO_WINDOW`) are verified adversarially.
4. **Progressive 4-Tier Hierarchy**: Tests are partitioned systematically into 4 escalating tiers, from unit-level feature isolation to full multi-step user journeys connecting video downloads directly into NovaCut's Editor and Review workflows.

---

## 2. Feature Inventory & Coverage Mapping

| Feature # | Feature Name | Source Requirement | Tier 1: Isolation | Tier 2: Boundary & Corner Cases | Tier 3: Cross-Feature Flows | Tier 4: Real-World Scenarios |
|---|---|---|---|---|---|---|
| **F1** | Runtime Detection & Validation | `ORIGINAL_REQUEST §R2` | Validate auto-discovery, missing binaries (`java.exe`, `unidbg-sign.jar`, `server.pyc`) | Non-existent custom path, invalid override dir, partial corrupted installation | Auto-detect tool before trigger start in resolve flow | Seamless tool detection during full user download session |
| **F2** | Process Lifecycle & Win32 Job Object | `ORIGINAL_REQUEST §R2` | Verify Job Object creation, `KILL_ON_JOB_CLOSE`, `CREATE_NO_WINDOW` flags | Process crash simulation, abnormal child exit recovery, port collision (9099 occupied) | Start -> Verify Ports -> Process Teardown -> Verify clean exit | Long-running download session with clean teardown upon exit |
| **F3** | Healthcheck & Status API | `ORIGINAL_REQUEST §R2` | `/api/hongguo/status` returns full state schema | Service stopped status, partial running status, corrupted config status | Status polling during service start & stop sequence | Status badge synchronization on UI tab entry |
| **F4** | Graceful Teardown Hooks | `ORIGINAL_REQUEST §R2` | `stop_services()` terminates subprocesses and closes Job Object | Force-kill simulation on hung child processes, double-stop invocation | Process launch -> Task execution -> Immediate graceful stop | NovaCut exit event handling without orphan processes |
| **F5** | License Backend Protection | `ORIGINAL_REQUEST §R4` | All `/api/hongguo/*` routes return HTTP 403 when unlicensed | License expiration mid-session, `CLOCK_TAMPERED` detection, malformed license cache | License failure blocks cascading downstream operations | Unlicensed user blocked from starting or downloading dramas |
| **F6** | Gateway API Proxy | `ORIGINAL_REQUEST §R2` | `/resolve`, `/episodes`, `/drama-detail`, `/submit`, `/tasks`, `/cancel` proxies | Empty input, malformed JSON, 502/504 upstream error handling | Resolve -> Parse Episodes -> Submit -> Tasks Polling -> Cancel | Complete API mediation during drama fetching & downloading |
| **F7** | Secure Path Registration | `ORIGINAL_REQUEST §R3` | Downloaded media registered in `routes.security.register_user_path` | Path traversal attempts (`../../windows`), unregistered paths rejected | Download completion triggers whitelist registration before playback | Video file automatically safe for HTML5 / WebView2 playback |
| **F8** | Native Dark Mode UI Tab | `ORIGINAL_REQUEST §R1` | Tab existence, dark mode styling tokens, glassmorphism containers | Rapid tab switching, zero `window.alert()` / `confirm()` | Tab activation checks license then triggers status poll | User opens Hongguo tab with seamless dark theme rendering |
| **F9** | Drama Parsing & Metadata Card | `ORIGINAL_REQUEST §R1` | Metadata parsing (title, cover, episodes count, tags, synopsis) | Invalid drama URL, nonexistent series ID, HTTP error response | Parse URL -> Render metadata card -> Populate episode list | User pastes drama link and instantly inspects drama metadata |
| **F10** | Episode Selector & Download Control | `ORIGINAL_REQUEST §R1` | Select All, range parser ("1-10, 15"), individual checkboxes | Inverted ranges ("10-1"), out-of-bounds numbers, invalid characters | Range selection -> Generate download payload -> Submit | User selects episodes 1-10 via range input box |
| **F11** | Real-time Download Progress Monitor | `ORIGINAL_REQUEST §R1` | Polling `/api/hongguo/tasks` updates progress bars, speeds, counts | Empty task queue, abrupt server disconnect during active download | Submit download -> Poll tasks progress -> Progress reaches 100% | Real-time progress monitoring through download lifecycle |
| **F12** | Workflow Bridges to Editor & Review | `ORIGINAL_REQUEST §R3` | `window.sendVideoToEditor`, `window.sendVideoToReview` functional | Paths with spaces, Unicode characters, non-existent files | Download episode -> Register path -> Bridge to Biên tập / Review | User downloads drama and sends video directly into Timeline |
| **F13** | Dark Mode Modal & Toast Alerts | `ORIGINAL_REQUEST §R1` | Zero `alert()`; all notices use `showAlertModal()` & `showToast()` | Error notifications with dark styling, modal overlay dismissal | API failure triggers Dark Mode modal -> Dismissal resumes UI | Graceful error handling in Dark Mode across entire journey |
| **F14** | Frontend License Permission Guard | `ORIGINAL_REQUEST §R4` | `checkFeaturePermission` gates tab switch and download buttons | Tampered client permission object, expired VIP plan status | Tab switch blocked -> License modal displayed -> Payment CTA | User without license prompted with VIP upgrade modal |

---

## 3. Test Architecture & Directory Layout

```
d:\Tool\AI-Movie-Shorts\AI-Movie-Shorts\
├── tests\
│   ├── test_hongguo_e2e.py                # Main 4-Tier E2E Test Suite (Milestone 3)
│   ├── test_hongguo_service.py            # M1 Unit tests for Process Manager
│   ├── test_hongguo_routes.py             # M1 Unit tests for Gateway API Blueprint
│   ├── test_hongguo_adversarial.py        # M1 Adversarial tests
│   ├── test_hongguo_frontend.py           # M2 Frontend static & structural tests
│   └── test_hongguo_challenger_bridges.py # M2 Playwright DOM & bridge tests
├── TEST_INFRA.md                          # This infrastructure & test mapping specification
├── TEST_READY.md                          # Execution report & readiness publication
└── .agents\teamwork\
    └── teamwork_preview_test_writer_m3\  # Working directory for M3 Test Writer
        ├── BRIEFING.md
        ├── DISPATCH.md
        ├── progress.md
        └── handoff.md
```

### 3.1 Tier Classification

- **Tier 1 — Feature Coverage (Isolation)**:
  Exercises each of the 14 features independently. Validates schema compliance, HTTP status codes, correct flag settings, Win32 Job Object attributes, and foundational license guards.
- **Tier 2 — Boundary & Corner Cases (Stress & Adversarial)**:
  Injects invalid, missing, empty, or malicious inputs. Tests path traversal attempts, port collisions, abnormal process crashes, mid-session license revocation, and clock tampering.
- **Tier 3 — Cross-Feature Combinations (Integration)**:
  Connects sequential features into multi-component chains. Validates that intermediate outputs (e.g. resolved drama ID, parsed episode ranges) feed accurately into subsequent stages (submit download, tasks progress polling, media path registration, editor bridges).
- **Tier 4 — Real-World Application Scenarios (End-to-End User Journeys)**:
  Executes complete end-to-end user journeys mirroring authentic usage: pasting a drama URL, parsing metadata, selecting episodes, executing downloads, verifying downloaded media integrity, registering security whitelist, and loading into NovaCut Editor and Review timelines.

---

## 4. Execution Protocol & Verification Command

```powershell
# Run the complete 4-tier E2E test suite
python -m pytest tests/test_hongguo_e2e.py -v
```

All tests must pass (100% pass rate) with zero unhandled exceptions, zero leaked processes, and zero test skips under standard test environments.
