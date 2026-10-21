@echo off
rem ===========================================================================
rem Builds the ReelVault Android capture app (debug APK) and copies it to dist\ReelVault.apk.
rem Checks for a JDK (17+) and the Android SDK first and explains what to install if missing.
rem ===========================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
set "ROOT=%cd%"

echo [1/4] Checking for a JDK ...
where java >nul 2>&1
if errorlevel 1 (
  if defined JAVA_HOME (
    if exist "%JAVA_HOME%\bin\java.exe" (set "PATH=%JAVA_HOME%\bin;%PATH%") else (goto :nojdk)
  ) else (
    goto :nojdk
  )
)
for /f "tokens=3" %%v in ('java -version 2^>^&1 ^| findstr /i "version"') do set "JAVAVER=%%~v"
echo       java %JAVAVER%
echo !JAVAVER! | findstr /r "^1\.8 ^9\. ^10\. ^11\. ^12\. ^13\. ^14\. ^15\. ^16\." >nul && (
  echo [FAIL] JDK 17 or newer is required ^(found !JAVAVER!^).
  goto :nojdk_hint
)

echo [2/4] Checking for the Android SDK ...
set "SDK="
if defined ANDROID_HOME if exist "%ANDROID_HOME%\platforms" set "SDK=%ANDROID_HOME%"
if not defined SDK if defined ANDROID_SDK_ROOT if exist "%ANDROID_SDK_ROOT%\platforms" set "SDK=%ANDROID_SDK_ROOT%"
if not defined SDK if exist "%LOCALAPPDATA%\Android\Sdk\platforms" set "SDK=%LOCALAPPDATA%\Android\Sdk"
if not defined SDK if exist "android\local.properties" (
  for /f "usebackq tokens=1,* delims==" %%a in ("android\local.properties") do if "%%a"=="sdk.dir" set "SDK=%%b"
  set "SDK=!SDK:\\=\!"
  set "SDK=!SDK:\:=:!"
)
if not defined SDK goto :nosdk
if not exist "%SDK%\platforms\android-35" (
  echo [FAIL] Android SDK found at %SDK% but platform android-35 is missing.
  echo        Install it with:  "%SDK%\cmdline-tools\latest\bin\sdkmanager.bat" "platforms;android-35" "build-tools;35.0.0"
  pause
  exit /b 1
)
echo       SDK at %SDK%
set "SDKESC=%SDK:\=\\%"
> "android\local.properties" echo sdk.dir=%SDKESC%

echo [3/4] Building with Gradle (first run downloads Gradle and dependencies; internet needed once) ...
pushd android
call gradlew.bat --no-daemon :app:assembleDebug
set "RC=%errorlevel%"
popd
if not "%RC%"=="0" (
  echo [FAIL] Gradle build failed ^(exit code %RC%^). Scroll up for the first error line.
  pause
  exit /b %RC%
)

echo [4/4] Copying APK ...
if not exist dist mkdir dist
copy /y "android\app\build\outputs\apk\debug\app-debug.apk" "dist\ReelVault.apk" >nul || (echo [FAIL] APK not found & pause & exit /b 1)
echo.
echo [OK] dist\ReelVault.apk
echo      Install on the phone: copy the file over USB and open it, or run  adb install -r dist\ReelVault.apk
echo      Allow "install from unknown sources" when prompted. This is a debug-signed build for personal use.
pause
exit /b 0

:nojdk
echo [FAIL] No Java runtime found on PATH or JAVA_HOME.
:nojdk_hint
echo        Install JDK 17: winget install Microsoft.OpenJDK.17   ^(or https://adoptium.net/^)
echo        Then open a NEW terminal and run build_apk.bat again.
pause
exit /b 1

:nosdk
echo [FAIL] Android SDK not found.
echo        Option A ^(easiest^): install Android Studio from https://developer.android.com/studio and open android\ once;
echo                 it installs the SDK to %%LOCALAPPDATA%%\Android\Sdk.
echo        Option B ^(command line only^): download "Command line tools only" from https://developer.android.com/studio#command-line-tools-only,
echo                 unzip to C:\Android\cmdline-tools\latest, then run:
echo                 C:\Android\cmdline-tools\latest\bin\sdkmanager.bat --sdk_root=C:\Android "platform-tools" "platforms;android-35" "build-tools;35.0.0"
echo                 and set ANDROID_HOME=C:\Android ^(setx ANDROID_HOME C:\Android^).
echo        Then run build_apk.bat again.
pause
exit /b 1
