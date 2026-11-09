[app]
title = Simomatch
package.name = simomatch
package.domain = org.simomatch
source.dir = .
source.include_exts = py,kv,atlas,png,jpg,jpeg,webp,wav,mp3,json
source.exclude_dirs = venv,.git,.idea,.buildozer,bin,.kivy_runtime,.pytest_cache,.test_runtime,.smoke_runtime,data,tests,tools,__pycache__
version = 0.1.2
requirements = python3,kivy==2.3.1,pyjnius
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a
# IMPORTANT: merge these keys into the WSL spec too if rsync excludes this file.
# python3 tools/check_android_capture.py --apply --spec buildozer.spec
# android.add_aars provides the manifest only; add_src compiles Java into DEX.
android.api = 36
android.permissions = FOREGROUND_SERVICE, FOREGROUND_SERVICE_MEDIA_PROJECTION, RECORD_AUDIO
android.add_src = android_src
android.add_aars = android_src/capture_manifest.aar
# p4a copies named AAR dependencies to the generated Gradle project's libs/.
android.add_gradle_repositories = flatDir { dirs 'libs' }
android.add_compile_options = "sourceCompatibility = 1.8", "targetCompatibility = 1.8"

[buildozer]
log_level = 2
