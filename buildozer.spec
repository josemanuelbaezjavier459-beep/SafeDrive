[app]
title = SafeDrive
package.name = safedrive
package.domain = org.safedrive

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 0.1

requirements = python3,kivy,pyjnius

orientation = portrait
fullscreen = 0

# Android API levels (good baseline for BLE + modern devices)
android.minapi = 24
android.api = 34
android.ndk_api = 24
android.sdk_path = /usr/local/lib/android/sdk
android.accept_sdk_license = True
android.skip_update = True

# Permissions required for BLE scanning/connection on Android
android.permissions = BLUETOOTH,BLUETOOTH_ADMIN,ACCESS_FINE_LOCATION,BLUETOOTH_SCAN,BLUETOOTH_CONNECT

# Keep arm64 as primary target for modern Android devices
android.archs = arm64-v8a

# AndroidX is required by recent toolchains
android.enable_androidx = True

[buildozer]
log_level = 2
warn_on_root = 1
