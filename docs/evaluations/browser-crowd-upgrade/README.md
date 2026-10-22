# Browser crowd and video upgrade

The website previously used one Full pose model with a four-person limit and JPEG previews paced at 8–12 fps. The release adds compressed browser video targeting 40 fps, CPU crowd skeleton observation, and the existing fast Full motion checks. Video, crowd observations, and motion checks have separate clocks and budgets.

## Model choice and limits

The pinned [RTMO-t body7 model](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/configs/body_2d_keypoint/rtmo/body7/rtmo_body7.md) observes people in one pass. Its actual SDK input is 416×416 BGR float32, despite the upstream table's 640 entry. [The manifest](model-manifest.json) records source, tensor contract and SHA-256 checksums. The model is 27,342,008 bytes. Only its 17 observed COCO joints map into the nullable 33-slot camera protocol; hands, heels and toes are left absent.

Product person admission is 0.25, matching the existing person detector's nominal floor. Paired box/pose suppression preserves the existing 0.65 IoU admission after clipping. Neither score is a calibrated fight probability.

Actual browser CPU tests on the Mac found all 20 people in each of three samples of a synthetic 20-person fixture. This is a coverage check on tiled images, not a real classroom accuracy test. The same production worker took median 295 ms on F07, 280 ms on C01 and 332 ms on the dense fixture with two WASM threads. These are roughly three crowd observations per second, not 40 pose updates per second.

Both tested GPU backends were rejected. The native WebGPU backend and legacy JSEP backend returned 32 capped detections on the 20-person fixture. Faster incorrect output is not enabled in the release. All 106 production CPU/GPU reports passed the server schema; valid transport is separate from correct model output.

Fast Full motion remains separate from CPU crowd observation. Its four-pose coverage limit remains visible through the checked-person count. Crowd observation does not create a second set of motion alerts. The original visibility, arm-motion and three-episode gates remain; the crowd profile uses per-pair cooldown so independent observed pairs do not share one camera-wide cooldown. Synthetic rule tests cover two independent interactions and nine pairs. They do not establish real fight accuracy.

F07 is a positive grab/push clip and C01 is a negative busy-hall clip, each five seconds. Both yielded zero alerts with the original rules, including with the new crowd poses. F07 remains a missed incident. This release does not establish 90% fight accuracy, complete 20-student motion coverage, or 40 fps on an iPhone.

## Video and recovery

The browser requests a source up to 60 fps and encodes observed frames toward 40 fps using H264. A deadline accumulator avoids accidentally reducing a 60 fps source to 30 fps. The wall counts frames actually drawn; it does not display the requested encoder rate as measured fps.

Encoder and socket queues are bounded. Backpressure drops work and resumes at a keyframe. Reconnect keeps the camera stream and detectors warm, resets the compressed-video generation, and requires fresh acknowledgements. Unsupported, failed or stalled encoders fall back to JPEG. JPEG capture has a deadline so a hung capture cannot block fallback. Stopping releases callbacks, timers, encoder and camera tracks.

The [local browser video check](local-video-result.json) measured 40 displayed fps in a five-second steady window, with no decoder errors or dropped display frames. It used synthetic moving pixels in the Mac browser without model load or public transport. It is not an iPhone result.

The public test uses its own isolated temporary workspace and synthetic moving video. It measures actual encoded and displayed frame deltas, checks changing pixels and fresh model reports, then forces three camera/wall reconnects. It deletes only that temporary workspace. Raw footage, landmarks and credentials remain in ignored private test output.

```sh
NIVRA_QA_RELEASE_READY=1 node scripts/evaluation/browser-speed/run.cjs
```

Public deployment results are recorded separately after the release check completes.
