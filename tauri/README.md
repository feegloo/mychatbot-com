# ChatRAG — Tauri Mobile & Desktop Wrapper

Tauri 2.0 native shell for ChatRAG. The web UI lives in `../frontend` (Vue 3 + TypeScript); this folder is a thin native wrapper that packages it for iOS, Android, and desktop.

```
tauri/
├── package.json          # wrapper scripts (all web work delegates to ../frontend)
├── scripts/
│   └── publish-appstore.sh
└── src-tauri/
    ├── tauri.conf.json   # points frontendDist → ../frontend/dist
    ├── Cargo.toml
    └── src/
        ├── main.rs       # desktop entry point
        └── lib.rs        # mobile entry point + Tauri commands
```

---

## Cloud / Local mode

The app ships with an **Apple-style toggle** in the top-centre of the screen that lets users switch between two modes:

| Mode | Label | What it does |
|------|-------|-------------|
| ☁️ Cloud | `Cloud` | Connects to **chatrag.app** — uses hosted LLMs and the full ChatRAG cloud backend. |
| 💻 Local | `Local` | Connects to a **locally running LLM** (Ollama). All data stays on-device — no internet required. |

Hovering over a label for **1 second** shows a tooltip:

- **Cloud** → _"use LLM (models) from chatrag.app"_
- **Local** → _"use private LLM (models) — "offline mode""_

The chosen mode is persisted in `localStorage` across restarts.

### macOS System Tray

When running as a macOS `.app`, ChatRAG places a monochrome cloud icon in the **menu bar** (system tray). Clicking it shows a dropdown menu:

```
● Running
Mode: Cloud ☁️
──────────────
Switch to Local 🖥
──────────────
Quit ChatRAG
```

The menu updates immediately when the mode is toggled — no restart required. The implementation (`src-tauri/src/tray.rs`) follows the pattern from [stik_app by 0xMassi](https://github.com/0xMassi/stik_app) using Tauri 2.0's `TrayIconBuilder`:

- `icon_as_template(true)` — adapts to macOS dark/light mode automatically
- `show_menu_on_left_click(true)` — standard macOS tray behaviour
- `on_menu_event` — rebuilds the menu after a mode toggle so the labels stay in sync

### Toggle implementation

The toggle is a self-contained Vue component (`frontend/src/components/TauriModeToggle.vue`) rendered only when the app detects it is running inside a Tauri shell (`window.__TAURI_INTERNALS__` present). It is mounted as a fixed overlay in `App.vue` and is invisible in normal browser usage.

The Rust layer (`src-tauri/src/lib.rs`) exposes three Tauri commands:

| Command | Description |
|---------|-------------|
| `get_mode` | Returns the current mode string (`"cloud"` or `"local"`). |
| `set_mode(mode)` | Persists the mode in the Rust process state (in-memory). |
| `check_ollama` | Probes `http://localhost:11434/api/tags`; returns `true` if Ollama is reachable. |

### Local mode — Ollama setup

1. **Install Ollama** from [ollama.com](https://ollama.com):

   ```bash
   # macOS
   brew install ollama
   # or download the .app from https://ollama.com/download/mac
   ```

2. **Pull a model** (a small, fast model works well on Apple Silicon):

   ```bash
   ollama pull llama3.2        # ~2 GB — recommended
   # or
   ollama pull phi3            # ~2.3 GB
   # or
   ollama pull mistral         # ~4 GB
   ```

3. **Start Ollama** (it starts automatically as a service after installation):

   ```bash
   ollama serve   # if not already running; default port 11434
   ```

4. Launch the ChatRAG Tauri app and flip the toggle to **Local**. The app calls `check_ollama` to confirm the service is reachable before routing queries there.

#### Apple Silicon / MLX note

On M-series Macs, Ollama uses **Apple MLX** automatically for accelerated inference — no extra setup needed. For direct MLX integration (without Ollama as middleware), see:

- [ml-explore/mlx-lm](https://github.com/ml-explore/mlx-lm) — Python bindings for running LLMs with MLX
- [LostRuins/koboldcpp](https://github.com/LostRuins/koboldcpp) — local inference server with OpenAI-compatible API, supports Metal acceleration

#### iOS / on-device note

Running an LLM fully on-device on iPhone/iPad requires:

- A model quantised to fit in RAM (typically ≤ 4 GB for an iPhone 15 Pro)
- Integration with Core ML or MLX; the Ollama daemon **does not run on iOS**
- Alternatively, point "local" mode at an Ollama server running on a Mac on the same Wi-Fi network by changing the endpoint in the app settings

This is tracked as a future enhancement. For now, Local mode on iOS gracefully falls back to Cloud mode when Ollama is unreachable.

## Prerequisites

### Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
rustup default stable
```

iOS targets:

```bash
rustup target add aarch64-apple-ios aarch64-apple-ios-sim x86_64-apple-ios
```

Android targets (add after Android SDK is ready):

```bash
rustup target add aarch64-linux-android armv7-linux-androideabi i686-linux-android x86_64-linux-android
```

### iOS (macOS only)

1. Install full **Xcode** from the Mac App Store — Command Line Tools alone are not enough.
2. Open Xcode once to accept the license.
3. Select the full Xcode toolchain:

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
```

4. Install CocoaPods:

```bash
brew install cocoapods
```

Verify:

```bash
xcodebuild -version && pod --version
```

### Android

1. Install **Android Studio** and through its SDK Manager install:
   - Android SDK Platform
   - SDK Command-line Tools
   - SDK Build-Tools
   - SDK Platform-Tools
   - Android NDK

2. Install Java 17:

```bash
brew install openjdk@17
```

3. Add to your shell profile (`~/.zshrc` or `~/.bash_profile`):

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
export ANDROID_HOME="$HOME/Library/Android/sdk"
export NDK_HOME="$ANDROID_HOME/ndk/$(ls "$ANDROID_HOME/ndk" | tail -1)"
export PATH="$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH"
```

4. Reload and verify:

```bash
source ~/.zshrc
java -version && adb --version
```

---

## Setup

```bash
cd tauri
npm install
npm run frontend:build   # builds ../frontend into ../frontend/dist
```

Generate native project files (run once after prerequisites are installed):

```bash
npm run ios:init         # generates src-tauri/gen/apple/
npm run android:init     # generates src-tauri/gen/android/
```

Generate app icons from a 1024×1024 source image:

```bash
npx tauri icon ../frontend/public/apple-touch-icon.png
```

---

## Available Scripts

| Script                     | What it does                                  |
| -------------------------- | --------------------------------------------- |
| `npm run frontend:build`   | Build the Vue app into `../frontend/dist`     |
| `npm run frontend:dev`     | Start the Vue dev server on port 5173         |
| `npm run check`            | TypeScript type-check (delegates to frontend) |
| `npm run lint`             | ESLint (delegates to frontend)                |
| `npm run tauri:dev`        | Desktop dev mode                              |
| `npm run tauri:build`      | Desktop release build                         |
| `npm run ios:init`         | Generate Xcode project (run once)             |
| `npm run ios:dev`          | Run on iOS simulator / device                 |
| `npm run ios:build`        | iOS release build                             |
| `npm run android:init`     | Generate Android project (run once)           |
| `npm run android:dev`      | Run on Android emulator / device              |
| `npm run android:build`    | Android release build                         |
| `npm run publish:appstore` | Build + upload to App Store Connect           |

---

## Publishing to the App Store

### 1. Apple Developer account

1. Enroll at [developer.apple.com/programs](https://developer.apple.com/programs/).
2. Create the app record in [App Store Connect](https://appstoreconnect.apple.com/):
   - App name: **ChatRAG**
   - Bundle ID: `chatrag.app`
3. Fill in support URL, marketing URL, and privacy policy URL.

### 2. Signing

1. In Xcode open the generated project at `src-tauri/gen/apple/`.
2. Select the app target → **Signing & Capabilities**.
3. Enable **Automatically manage signing**.
4. Select your team; confirm the bundle ID matches App Store Connect.

### 3. App metadata to prepare

- App description and keywords
- Privacy policy URL
- 1024×1024 App Store icon (no alpha channel)
- iPhone screenshots (at minimum: 6.5″ and 5.5″)
- iPad screenshots (if iPad is supported)
- Demo login credentials for the review team
- Export compliance answers

### 4. Upload with `npm run publish:appstore`

Set three environment variables (create an app-specific password at [appleid.apple.com](https://appleid.apple.com)):

```bash
export APPLE_ID="you@example.com"
export APPLE_APP_SPECIFIC_PASSWORD="abcd-efgh-ijkl-mnop"
export APPLE_TEAM_ID="XXXXXXXXXX"   # 10-char code from developer.apple.com/account
```

Then:

```bash
cd tauri
npm run publish:appstore
```

The script will:

1. Run `tauri ios build --release`
2. Locate the generated `.ipa`
3. Upload it via `xcrun altool` (or Transporter as fallback)
4. Print the App Store Connect URL when done

To upload an already-built IPA without rebuilding:

```bash
SKIP_BUILD=1 IPA_PATH=src-tauri/gen/apple/build/arm64/ChatRAG.ipa npm run publish:appstore
```

Apple processes the build for 5–30 minutes after upload. You'll receive an email when it's available in App Store Connect for TestFlight or review submission.

Docs: [developer.apple.com/help/app-store-connect/manage-builds/upload-builds](https://developer.apple.com/help/app-store-connect/manage-builds/upload-builds/)

### 5. Submit for review

1. Go to App Store Connect → your app → **App Store** tab.
2. Select the processed build.
3. Complete **App Privacy** questionnaire.
4. Complete **Export Compliance**.
5. Click **Submit for Review**.

---

## Publishing to Google Play

### 1. Google Play Console

1. Create account at [play.google.com/console](https://play.google.com/console/).
2. Create app: **ChatRAG**, bundle: `chatrag.app`.
3. Complete store listing, data safety form, and privacy policy.

### 2. Release flow

```bash
cd tauri
npm run android:build    # produces .aab in src-tauri/gen/android/
```

Upload the `.aab` to **Internal testing** first, then promote through:

1. Internal testing → validate login, uploads, subscriptions
2. Closed testing (beta)
3. Production rollout

---

## Payments: Stripe vs Apple IAP

| Scenario                           | iOS App Store                                       | Android / Web |
| ---------------------------------- | --------------------------------------------------- | ------------- |
| Physical goods or off-app services | Stripe ✅                                           | Stripe ✅     |
| Digital subscriptions / AI credits | **Apple IAP required** (guideline 3.1.1)            | Stripe ✅     |
| External payment link (US only)    | Apple StoreKit External Purchase entitlement needed | N/A           |

**Recommendation for ChatRAG:** use Apple In-App Purchase for iOS digital subscriptions/credits; keep Stripe for the web app and Android.

Apple Pay is not a substitute for Apple IAP — it is for eligible physical/service transactions, not for unlocking digital app features.

---

## Linting and type-checking

```bash
cd tauri
npm run lint     # runs ESLint on ../frontend
npm run check    # runs vue-tsc on ../frontend
```
