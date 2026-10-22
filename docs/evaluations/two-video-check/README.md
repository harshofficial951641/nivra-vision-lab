# Two-video detection check

The requested 90% accuracy target is **not verified**. The current trained detector missed the declared grabbing/pushing incident. The isolated modified Full pose detector missed it too. A fresh replay of the exact historical browser skeleton rules also missed it. Both left the normal corridor clip without an alert.

| Preselected video | Expected | Native X3D scene logic | Modified Full pose rules |
|---|---|---|---|
| F07, rail employee grabbed/pushed | Review alert | Missed | Missed |
| C01, normal busy school corridor | No alert | No alert | No alert |

Each path matched one of two declared clip outcomes. This is not an estimate of deployment accuracy. Training overlap is unknown, and the clips have no independent dense action/person annotations. Neither test exercises twenty students or simultaneous fights.

The clips were selected before inference from existing local footage. SHA-256 hashes identify the exact files in [native results](native-results.json) and [pose summary](pose-summary.json). The native replay used the actual float32 Core ML model, shared native preprocessing/window helpers and the unchanged scene decision function on Mac CPU. The pose comparison ran the existing Full VIDEO worker and unchanged ConflictEngine/DeviceAnalysis in Chromium GPU. The complete app, asynchronous transport and phone runtime were not part of these isolated replays.

The model's highest publisher score on F07 was 0.3801, below its existing 0.4 candidate threshold. In the denser pose replay, two poses appeared in only one of 75 unique frames. This identifies failures in both scene classification and pose coverage. Scores are not calibrated violence probabilities. Lowering thresholds until these two examples pass would fit the test clips rather than establish accuracy.

See the [native protocol and per-window findings](native-report.md) and [pose protocol and coverage findings](pose-report.md) for reproduction and limitations. Raw clips and extracted frames remain local and are excluded from Git and deployment.

The next accuracy check needs separate development and untouched test videos, with declared action intervals and multiple camera angles. Include normal crowd movement, greetings, play, occlusion and camera shake as negative examples. Measure incident recall, false alerts per minute and time to first alert separately. Tune or retrain using development footage, then evaluate the frozen system once on the untouched set.

Playback and pairing fixes passed 529 web tests, 45 backend camera/connection tests and 36 native tests. Those checks establish software behavior, not fight-detection accuracy. One physical iPhone delivered about 40 encoded frames per second to the Mac. After fixing display timer starvation and clock drift, two ten-second samples drew 39.96 fps and 35.82 fps on the actual camera wall. Both stayed on native video; the second sample dropped frames during timing recovery. The [metadata-only playback proof](physical-playback.json) records both windows. This verifies one-phone playback, not crowded-scene detection or four-camera performance.

The [fresh historical browser skeleton replay](original-pose-report.md) used the restored published source, Full VIDEO mode and the CPU delegate. Both engines received identical actual landmarks from 75 unique frames per clip. F07 produced no alert; C01 stayed quiet. This verifies the restored path and records its coverage failure, without an accuracy claim.
