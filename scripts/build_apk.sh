#!/usr/bin/env bash
# ===========================================================================
# Builds the ReelVault Android capture app (debug APK) on macOS/Linux and copies it to dist/ReelVault.apk.
# Checks for a JDK (17+) and the Android SDK first and explains what to install if missing.
# Run:  bash scripts/build_apk.sh
# ===========================================================================
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

echo "[1/4] Checking for a JDK ..."
if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then export PATH="$JAVA_HOME/bin:$PATH"; fi
if ! command -v java >/dev/null 2>&1; then
  echo "[FAIL] No Java runtime found."
  echo "       Install JDK 17 with Homebrew:   brew install --cask temurin@17"
  echo "       or download it from https://adoptium.net/temurin/releases/?version=17 (macOS .pkg, pick aarch64 for Apple Silicon)."
  echo "       Then open a NEW terminal and run this script again."
  exit 1
fi
JAVAVER=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+)(\.[0-9]+)?.*/\1/')
echo "      java major version $JAVAVER"
if [ "${JAVAVER:-0}" -lt 17 ] 2>/dev/null; then
  echo "[FAIL] JDK 17 or newer is required. Install:  brew install --cask temurin@17"
  exit 1
fi

echo "[2/4] Checking for the Android SDK ..."
SDK=""
for cand in "${ANDROID_HOME:-}" "${ANDROID_SDK_ROOT:-}" "$HOME/Library/Android/sdk" "$HOME/Android/Sdk"; do
  if [ -n "$cand" ] && [ -d "$cand/platforms" ]; then SDK="$cand"; break; fi
done
if [ -z "$SDK" ] && [ -f android/local.properties ]; then
  SDK=$(sed -n 's/^sdk.dir=//p' android/local.properties | sed 's/\\:/:/g; s/\\\\/\\/g')
fi
if [ -z "$SDK" ] || [ ! -d "$SDK/platforms" ]; then
  echo "[FAIL] Android SDK not found."
  echo "       Option A (easiest): install Android Studio from https://developer.android.com/studio, open it once"
  echo "                (it installs the SDK to ~/Library/Android/sdk), then run this script again."
  echo "       Option B (command line only):"
  echo "                brew install --cask android-commandlinetools"
  echo "                sdkmanager --install \"platform-tools\" \"platforms;android-35\" \"build-tools;35.0.0\""
  echo "                export ANDROID_HOME=\"\$(brew --prefix)/share/android-commandlinetools\""
  echo "       Then run this script again."
  exit 1
fi
if [ ! -d "$SDK/platforms/android-35" ]; then
  echo "[FAIL] Android SDK found at $SDK but platform android-35 is missing. Install it with:"
  echo "       \"$SDK/cmdline-tools/latest/bin/sdkmanager\" \"platforms;android-35\" \"build-tools;35.0.0\""
  echo "       (or Android Studio > Settings > Languages & Frameworks > Android SDK > tick Android 15 / API 35)"
  exit 1
fi
echo "      SDK at $SDK"
printf 'sdk.dir=%s\n' "$SDK" > android/local.properties

echo "[3/4] Building with Gradle (first run downloads Gradle and dependencies; internet needed once) ..."
chmod +x android/gradlew
( cd android && ./gradlew --no-daemon :app:assembleDebug )
RC=$?
if [ $RC -ne 0 ]; then
  echo "[FAIL] Gradle build failed (exit code $RC). Scroll up for the first error line."
  exit $RC
fi

echo "[4/4] Copying APK ..."
mkdir -p dist
cp -f android/app/build/outputs/apk/debug/app-debug.apk dist/ReelVault.apk || { echo "[FAIL] APK not found"; exit 1; }
echo
echo "[OK] dist/ReelVault.apk"
echo "     Install on the phone: AirDrop/USB-copy the file and open it, or  adb install -r dist/ReelVault.apk"
echo "     Allow \"install from unknown sources\" when prompted. This is a debug-signed build for personal use."
