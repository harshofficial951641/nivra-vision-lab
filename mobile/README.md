# NIVRA mobile apps

The Android and iPhone apps connect to `https://nivra.tanishq.work`. Each has Camera, Guard, and Camera wall roles, native QR scanning, and a paste-link option. Sessions stay in the platform's persistent WebView cookie store.

## Built downloads

These files are ready in this checkout. Sizes and SHA-256 hashes were checked against the built binaries.

| File | Bytes | Use |
| --- | ---: | --- |
| [Nivra-Android.apk](artifacts/Nivra-Android.apk) | 2,500,187 | Installable Android debug build |
| [Nivra-iPhone-Development.ipa](artifacts/Nivra-iPhone-Development.ipa) | 1,900,492 | Signed development build for registered iPhones/iPads |
| [Nivra-iOS-Simulator.zip](artifacts/Nivra-iOS-Simulator.zip) | 2,056,501 | iOS Simulator app; cannot install on a physical phone |

[SHA256SUMS](artifacts/SHA256SUMS) contains the full hashes. Verify the downloads from the repository root:

```bash
cd mobile/artifacts
shasum -a 256 -c SHA256SUMS
```

## Install on Android

Requires Android 8 or newer. Download the APK on the phone, open it, and allow installation from that download source when Android asks. Alternatively, connect an Android device with USB debugging enabled and run:

```bash
adb install -r mobile/artifacts/Nivra-Android.apk
```

This is a locally signed **debug build**, not a Play Store release. Package ID is `work.tanishq.nivra`, version `0.1.0`. Updates must use the same signing key. The signing certificate's public SHA-256 fingerprint is:

```text
BB:40:40:80:18:84:D3:14:9D:61:15:63:9C:7E:C0:F9:07:D7:D1:30:F8:7E:5C:CA:B8:F8:6A:A5:05:1B:F5:5D
```

The QR scanner uses Google Play services and may download its scanner module on first use. If the module is unavailable, use Paste pairing link.

Rebuild with `bash mobile/scripts/build-android.sh`. It runs four URL-policy tests, Android lint, and APK assembly. The local toolchain uses JDK 21, Gradle 8.9, and Android SDK 35 under `~/.cache/nivra-mobile`. The script also accepts `JAVA_HOME`, `ANDROID_HOME`, and `NIVRA_GRADLE_BIN`. Raw build output is `mobile/android/app/build/outputs/apk/debug/app-debug.apk`; the distributed copy above has the same hash.

## Install on iPhone or iPad

Requires iOS 17 or newer. The IPA is signed for the **four devices registered in its development provisioning profile**, which expires on **22 October 2027**. It is not a public App Store or TestFlight release. Downloading it in Safari does not make an unregistered phone eligible to install it.

For a connected, unlocked, trusted iPhone already in the profile, run `python3 mobile/scripts/install-ios-connected.py` from the repository root. It checks the profile, installs NIVRA, and verifies a real-device process launch. Completed installs for the current binary are recorded locally so later runs skip them. You can select a phone with `--name 'Phone display name'`. If a newly connected phone is missing from the signing profile, add `--register-missing` to let Xcode use automatic provisioning with the existing development team, then install. The phone must be unlocked, trusted, and have Developer Mode enabled.

You can also install on an eligible device through Xcode's Devices and Simulators window or Apple Configurator. A different device needs to be registered with the signing team and the app rebuilt with an updated profile. The simulator ZIP is only for iOS Simulator.

Open [ios/Nivra.xcodeproj](ios/Nivra.xcodeproj) in Xcode, or rebuild from the repository root:

```bash
./mobile/scripts/build-ios.sh
./mobile/scripts/build-ios-device.sh
```

The project is generated from `mobile/ios/project.yml` using XcodeGen. The signed build uses the workspace owner's installed development team by default; set `NIVRA_APPLE_TEAM` to select another team. Bundle ID is `work.tanishq.nivra.ios`.

## Pair and run

Choose a role, then scan or paste the matching invite created for your site. Camera and guard tokens remain in URL fragments. Owner invites use `/wall#operator=TOKEN`. HTTPS pairing links must belong to `nivra.tanishq.work`. Custom forms `nivra://camera#pair=TOKEN`, `nivra://guard#pair=TOKEN`, and `nivra://wall#operator=TOKEN` are also accepted. Tokens are not written to native app preferences or logs.

The iOS app declares `applinks:nivra.tanishq.work`, with app ID `422C63R2G8.work.tanishq.nivra.ios`. Universal Links require the hosted Apple association file; Android App Links require the hosted `assetlinks.json` to match its package and signing fingerprint. Native QR scanning and paste work independently of automatic link association.

Allow camera access for Camera or QR scanning and location access for camera/guard GPS. Camera grants are restricted to the trusted service; microphone requests are denied. GPS does not determine an indoor floor. Set the floor manually in the guard app or site Setup.

Camera processing and guard GPS work **while the app is open**. Moving the app to the background stops its media/location activity. Returning reloads the page; start the camera again when ready. Google Maps links open outside the app. Native background capture, background guard tracking, APNs/FCM, and native background push are not implemented. Keep the guard app open to receive its live alerts.

## Verification and remaining checks

- Both iOS Simulator and signed device builds succeeded. Three iOS URL-policy XCTest cases passed.
- Native iOS role selection, launch, camera permission denial, and network-error recovery were inspected in the T3 Device panel. A screenshot is saved at [ios-role-picker.png](artifacts/ios-role-picker.png).
- iOS Simulator public-page loading was blocked by this Mac's DNS cache. WebKit reported `NSURLErrorDomain -1003`; TLS checks were not bypassed.
- Android APK assembly, signature verification, and four URL-policy tests passed. Android lint had zero errors and two optional icon warnings.
- Installation and process launch succeeded on one registered physical iPhone. Additional phones are being connected separately. Real camera/QR capture, GPS accuracy, ML throughput, Android installation, and automatic link association still need device verification. No Android runtime test or native background-push delivery is claimed.

## Platform references

- [Apple WebKit media permission delegate](https://developer.apple.com/documentation/webkit/wkuidelegate/webview(_:requestmediacapturepermissionfor:initiatedbyframe:type:decisionhandler:))
- [Android WebChromeClient permissions](https://developer.android.com/reference/android/webkit/WebChromeClient)
- [Android command-line SDK tools](https://developer.android.com/studio)
