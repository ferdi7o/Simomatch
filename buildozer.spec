[app]
title = Simomatch
package.name = simomatch
package.domain = org.simomatch
source.dir = .
source.include_exts = py,kv,atlas,png,jpg,jpeg,webp,wav,mp3,json
source.exclude_dirs = venv,.git,.idea,.buildozer,bin,.kivy_runtime,.pytest_cache,.test_runtime,.smoke_runtime,data,tests,tools,__pycache__
version = 0.1.0
requirements = python3,kivy==2.3.1,pyjnius
orientation = portrait
fullscreen = 0
android.archs = arm64-v8a

[buildozer]
log_level = 2
