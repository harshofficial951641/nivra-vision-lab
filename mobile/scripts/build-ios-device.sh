#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/../ios"
xcodegen generate
NIVRA_BUILD_TEAM="${NIVRA_APPLE_TEAM:-422C63R2G8}"
xcodebuild -project Nivra.xcodeproj -scheme Nivra -configuration Debug -sdk iphoneos -destination 'generic/platform=iOS' -derivedDataPath ../build/ios-device DEVELOPMENT_TEAM="$NIVRA_BUILD_TEAM" CODE_SIGN_STYLE=Automatic -allowProvisioningUpdates build
mkdir -p ../build/package/Payload ../artifacts
ditto ../build/ios-device/Build/Products/Debug-iphoneos/Nivra.app ../build/package/Payload/Nivra.app
(cd ../build/package && /usr/bin/zip -qr ../../artifacts/Nivra-iPhone-Development.ipa Payload)
