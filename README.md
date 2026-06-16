# Mobile Crawler

AI-powered Android app exploration tool. Automatically crawls the UI of an Android app, maps navigation paths, captures screenshots, and records a path graph of every screen and transition discovered.

---

## Crawl Modes

### OmniParser Sweep (recommended)
Deterministic, LLM-free traversal driven by a local [OmniParser](https://github.com/microsoft/OmniParser) vision server. Each screen is parsed once for bounding boxes, then every element is tapped in order (top-to-bottom, left-to-right). After each tap, the crawler checks whether a new screen was reached, records the navigation edge, and returns to the base screen before continuing to the next element.

- No per-step LLM cost — fast and repeatable.
- Attempts carousel detection (a single bounding box that navigates to multiple destinations via sub-region probing).
- Attempts popup/dropdown handling (re-parses after in-place changes, taps newly appeared elements).
- Builds a path graph (node = screen, edge = element tap) viewable in the GUI.
- Requires a running local OmniParser server (see [Setup](#omniparser-setup)).

#### Known Limitations

**Screen identity for single-activity apps (React Native)**
Screen deduplication uses `package/activity` as the identifier. For apps that host many screens inside one Activity (e.g. React Native's `ReactActivity`), this causes all those screens to be treated as one node — unless a stable UI title can be read from the accessibility hierarchy. Title lookup is unreliable when the first visible text is dynamic content (search suggestions, personalised feeds, counters). This is a fundamental limitation of Android's accessibility APIs for React Native apps and has no fully reliable fix without app instrumentation.

**Carousels**
Carousel detection is behavioural: after the center of a bounding box navigates somewhere, the crawler probes a 3×3 grid of sub-points within the box. If multiple distinct destinations are found, the element is marked as a carousel. This misses carousels whose items don't individually navigate (e.g. a swipeable image banner), and may misclassify large container boxes that happen to enclose two separate tappable elements.

**Popups and dropdowns**
When a tap causes an in-place change (pixel diff detected but activity unchanged), the crawler re-runs OmniParser to find newly appeared elements and taps them. This works for simple single-level popups. It does not reliably handle: nested modals more than 2 levels deep, bottom sheets that animate in slowly (may be missed if the settle delay is too short), or dropdowns that require a scroll to reveal all options.

**Animated elements**
A second "idle" screenshot is taken 0.5 s after each tap to measure background animation noise. Pixels still changing during the idle period are masked out of the tap diff. This reduces false positives from spinners and looping banners but does not eliminate them — fast animations that complete within the settle delay will still inflate the diff ratio and may be misclassified as in-place changes.

**No scroll support**
Elements below the fold are not discovered. The crawler only taps what OmniParser detects in the initial viewport screenshot. Scrollable lists, infinite feeds, and collapsed sections require manual scroll steps or a separate scroll-and-rescan pass (not yet implemented).

### DroidRun AI Agent
Delegates exploration to a DroidRun AI agent loaded from `external/droidrun`. An LLM decides each action. More exploratory but slower and non-deterministic.

---

## Quick Start

```bash
git clone <repository-url>
cd mobile-crawler

git submodule update --init --recursive

python -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\Activate.ps1       # Windows

pip install -e .
pip install -e external/droidrun   # DroidRun submodule
pip install -e ".[dev]"            # dev tools (pytest, ruff, black)
```

Start the GUI:

```bash
python -m mobile_crawler.ui.main_window
```

Or use the PowerShell launcher (Windows, starts MobSF container too):

```powershell
.\scripts\start.ps1
```

Run from the CLI:

```bash
python run_cli.py crawl \
  --device emulator-5554 \
  --package com.example.app \
  --provider gemini \
  --model gemini-1.5-flash \
  --steps 15
```

---

## Requirements

- Python 3.12
- Android device or emulator reachable via ADB
- For **OmniParser Sweep**: local OmniParser server running at `http://localhost:8000`
- For **DroidRun AI Agent**: AI provider credentials (Gemini, Anthropic, OpenRouter, or Ollama)
- `external/droidrun` git submodule initialized

Optional:
- Docker Desktop + MobSF for static APK analysis
- PCAPdroid for network traffic capture
- Android screen recording support

---

## Connect an Android Device

Install Android SDK Platform Tools so `adb` is on your PATH, then:

**USB:**
1. On the device: Settings → About phone → tap Build number 7× to unlock Developer Options.
2. Settings → Developer Options → enable USB Debugging.
3. Connect via USB, accept the authorization prompt on the device.

```bash
adb devices   # should show <device-id> device
```

**Wireless (Android 11+):**
1. Settings → Developer Options → Wireless Debugging → pair device.
2. Use the IP and port shown on the device.

```bash
adb pair 192.168.1.x:<pairing-port>
adb connect 192.168.1.x:5555
adb devices
```

---

## OmniParser Setup

OmniParser Sweep requires a local OmniParser server. The default URL is `http://localhost:8000` (configurable in Settings → General → OmniParser Local URL).

Clone and run OmniParser locally following the [OmniParser README](https://github.com/microsoft/OmniParser). Once running, verify:

```bash
curl http://localhost:8000/health
```

The GUI Settings → General tab shows the connection status and lets you adjust the detection threshold (`omniparser_box_threshold`, default `0.02`).

---

## GUI Overview

| Tab / Panel | What it does |
|---|---|
| **General Settings** | Crawl mode selector, OmniParser or DroidRun settings, device/package selection |
| **AI Settings** | API keys for Gemini, Anthropic, OpenRouter; Replicate key |
| **Run Controls** | Start/Stop crawl, live log output |
| **Run History** | Past runs, per-run stats, MobSF analysis trigger |
| **Path Graph** | Interactive node-edge graph of discovered screens and navigation edges. Nodes show screen thumbnails with element bounding boxes overlaid. Edges show the element thumbnail that was tapped. Carousel elements are highlighted in pink; regular elements in blue. Use the Reset Zoom button to fit the view. |

---

## Path Graph

The path graph is built automatically during an OmniParser Sweep crawl.

- **Nodes** — each unique screen discovered (identified by `package/activity/header-hash`).
- **Edges** — each element tap that caused navigation. Multiple edges between the same two nodes are fanned out in parallel so they are all visible.
- **Thumbnails on edges** — cropped screenshot of the element that was tapped (shown at the midpoint of the arrow).
- **Bounding box overlay on nodes** — blue boxes for regular elements, pink for carousels.

Screen deduplication uses a perceptual hash of the **header/title bar region** (10%–35% of screen height) with a Hamming distance threshold of 6. This region is stable within the same screen but unique across different screens, even within the same Android Activity.

---

## OmniParser Sweep — How It Works

1. Launch the target app and take a screenshot.
2. Send the screenshot to the local OmniParser server. Detected bounding boxes are filtered to exclude the status bar (top ~10% of the screen).
3. Sort elements top-to-bottom, left-to-right.
4. For each element:
   - Tap the element center.
   - Wait for the screen to settle.
   - Compare the screen signature before and after. If it changed → record a navigation edge.
   - **Sub-region probing**: tap a 3×3 grid within the element's bounding box. If multiple distinct destinations are found → mark the element as a **carousel** (pink bounding box).
   - Navigate back to the base screen (up to 5 back presses, relaunch if needed).
5. Add newly discovered screens to the breadth-first queue and repeat.

All edges are stored in the `omni_sweep_edges` table with `(run_id, from_signature, to_signature, from_bbox_json)` uniqueness so duplicate edges from repeated runs are ignored.

---

## DroidRun AI Agent Mode

Delegates the full exploration loop to DroidRun loaded from `external/droidrun`. Configure your AI provider in Settings → AI. Available providers: Gemini, Anthropic, OpenRouter, Ollama.

The `ui_parser_mode` setting controls how DroidRun reads the screen:

| Value | Behavior |
|---|---|
| `boost` (default) | Accessibility tree first, OmniParser fallback |
| `omniparser` | Always use OmniParser vision |
| `accessibility` | Accessibility tree only |

---

## MobSF Static Analysis

Run MobSF APK analysis after a crawl. Requires MobSF running separately (default `http://localhost:8000`).

**Start MobSF with Docker:**

```bash
docker pull opensecurity/mobile-security-framework-mobsf
docker run --rm -it --name mobile-crawler-mobsf -p 8000:8000 opensecurity/mobile-security-framework-mobsf
```

Or use the project launcher on Windows: `.\scripts\start.ps1`

**Configure API key** — Mobile Crawler resolves it automatically from:
1. `.mobsf_api_key` file in the repo root
2. Docker container logs (if using the managed container)
3. `CRAWLER_MOBSF_API_KEY` environment variable

Reports are saved under the run session folder:

```
output_data/run_{ID}_{timestamp}/reports/
```

---

## PCAPdroid Traffic Capture

1. Install PCAPdroid from Google Play on the device.
2. Enable TLS decryption in PCAPdroid settings and install PCAPdroid-mitm when prompted.
3. In PCAPdroid → Control Permissions → generate an API key.
4. Paste the API key in Mobile Crawler Settings → Integrations.
5. Enable Traffic Capture before starting a crawl.

Capture files are saved to `output_data/run_{ID}_{timestamp}/pcap/`.

---

## Session Artifacts

Each run creates a folder under `output_data/`:

```
output_data/
└── run_{ID}_{YYYYMMDD_HHMMSS}/
    ├── screenshots/     ← annotated bounding-box screenshots, arrival screenshots
    ├── reports/         ← MobSF JSON/PDF reports
    ├── pcap/            ← network traffic capture
    ├── videos/          ← screen recordings
    ├── logs/            ← JSONL debug logs
    ├── data/
    └── apks/            ← pulled APKs for MobSF upload
```

---

## Configuration

Default values are in [src/mobile_crawler/config/defaults.py](src/mobile_crawler/config/defaults.py). Key defaults:

| Key | Default | Description |
|---|---|---|
| `crawl_mode` | `droidrun` | `droidrun` or `omni_sweep` |
| `omni_sweep_mode` | `breadth` | `breadth` (recommended) or `depth` |
| `omniparser_local_url` | `http://localhost:8000` | Local OmniParser server |
| `omniparser_box_threshold` | `0.02` | Detection confidence threshold |
| `max_crawl_steps` | `15` | Max element taps per crawl |
| `max_crawl_duration_seconds` | `600` | Max crawl wall time |
| `ui_parser_mode` | `boost` | DroidRun mode only |

---

## Development

```bash
cd src && pytest
ruff check .
black .
pytest --cov=mobile_crawler --cov-report=html
```

Project layout:

```
src/mobile_crawler/
├── cli/              ← Click CLI entry point
├── config/           ← defaults, ConfigManager
├── core/             ← CrawlerLoop, pre-crawl validator
├── domain/           ← OmniParserSweepService, DroidRunAgentService,
│                        ADBActionExecutor, OmniParserClient, prompts, ...
├── infrastructure/   ← DatabaseManager, repositories, AIInteractionService
└── ui/               ← PySide6 MainWindow, widgets (PathGraphWidget, ...)
external/droidrun/    ← DroidRun submodule (AI agent runtime)
tests/
```

---

## License

MIT
