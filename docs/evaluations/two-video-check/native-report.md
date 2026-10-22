# Two declared clip checks

This is an isolated CPU-only replay of the current float32 Core ML model and native RGB/window/tensor helpers. It applies the unchanged scene decision function. No live alerts were created or thresholds changed.

The two clips were chosen before inference. They are not an independent holdout; training overlap is unknown. Labels describe the declared visible action, not dense human ground truth. These two outcomes cannot establish 90% accuracy.

| Clip | Window (s) | Backbone softmax | Publisher second softmax | Rectangle people / poses | New review alert | CPU inference |
|---|---:|---:|---:|---:|---|---:|
| F07 (native) | 0.000–3.800 | 0.005462 | 0.271095 | 2 / 1 | no | 1600 ms |
| F07 (native) | 0.200–4.200 | 0.026246 | 0.279386 | 1 / 1 | no | 1634 ms |
| F07 (native) | 0.600–4.600 | 0.068952 | 0.296902 | 3 / 2 | no | 1857 ms |
| F07 (declared-core) | 0.500–4.500 | 0.255411 | 0.380087 | 3 / 2 | no | 1983 ms |
| C01 (native) | 0.000–3.866 | 0.000518 | 0.269145 | 4 / 5 | no | 1713 ms |
| C01 (native) | 0.266–4.266 | 0.000577 | 0.269168 | 6 / 4 | no | 2002 ms |
| C01 (native) | 0.666–4.666 | 0.000990 | 0.269331 | 5 / 4 | no | 1734 ms |
| C01 (declared-core) | 0.533–4.533 | 0.001359 | 0.269476 | 3 / 4 | no | 1148 ms |

F07: 0 review alert(s), missed positive label. C01: 0 review alert(s), matched negative label. 1 of 2 declared clip outcomes matched. This is not an accuracy estimate.

modelScore is the existing backbone's class-1 softmax output, not a raw logit. publisherScore applies the existing publisher's second softmax to the two backbone outputs. The scene decision uses publisherScore. Neither score is a calibrated violence probability.

The isolated scene gate requires at least two rectangle detections, publisher score ≥0.4 on two windows no more than one second apart, or a single score ≥0.7, with an eight-second scene cooldown. Pose count does not replace rectangle count for this decision.

This replay does not exercise the active transport/runtime gates: ready state, video received within three seconds, source/report freshness, people/fight timestamp separation ≤1.5 seconds, socket report deduplication, or the persisted eight-second camera cooldown across reconnects. Here, person detections are computed from the same source frame as the fight window end. It therefore cannot establish end-to-end alert delivery.

The post-fix replay admits actual decoded frames at least 200 ms after the preceding admitted source PTS, with a 0.001 ms roundoff tolerance. It keeps source PTS without rescaling. Native windows use the existing ≥3.8-second readiness rule and ≥400 ms prediction interval. Exact source timestamps and bounds are in JSON.

The declared-core row independently checks nominal 0.5–4.5 seconds; its confirmation state is not mixed into the native cadence. The preserved baseline used a nearest 5 Hz source grid, so its native rows are not a controlled tolerance-only comparison. Core rows keep the same requested interval. The tolerance fixes floating-point boundary losses; model weights, preprocessing and score thresholds are unchanged.

BGRA decoding and CPU-only Vision were used on Mac. Phone capture can be NV12, and Vision can choose another processor on phone. This does not measure phone runtime, camera-angle generalization, busy-worker frame dropping, or end-to-end alert latency. First alert source time is null when no alert occurred. CPU inference excludes model load and compilation.

Reproduce from repository root:

```sh
mkdir -p test-results/native-two-clip
swiftc -O mobile/ios/Nivra/NativeFightVision.swift mobile/ios/Nivra/NativePeopleVision.swift mobile/scripts/evaluate-native-clips.swift -o /tmp/nivra-native-clip-eval
/tmp/nivra-native-clip-eval "/path/to/footage/fights/cuts"
service/.venv/bin/python mobile/scripts/report-native-clips.py "/path/to/footage/fights"
```
