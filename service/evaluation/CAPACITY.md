# Local multi-camera capacity smoke — 28 September 2026

Experimental RTMO + ByteTrack + regional SlowFast + X3D on GTX 1660 Ti 6 GB,
i5-10400F and 32 GB RAM. Each source repeats the same public two-person grapple.
12 FPS capture target; bounded RGB history; fair latest-job GPU queue. No live
mobile networks, real classrooms or 30–50-person throughput are represented.

| Concurrent sources | Source | Seconds | Frames received | Detection jobs completed | Jobs replaced | Detection FPS | Frame-ack p95 ms | Sampled whole-GPU MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2 | 1 | 60.35 | 678 | 276 | 401 | 4.57 | 10.8 | 2377–2413 |
| 2 | 2 | 60.35 | 679 | 278 | 400 | 4.61 | 11.4 | 2377–2413 |
| 4 | 1 | 60.54 | 679 | 105 | 572 | 1.73 | 13.8 | 2379–2412 |
| 4 | 2 | 60.54 | 678 | 105 | 572 | 1.73 | 13.9 | 2379–2412 |
| 4 | 3 | 60.54 | 679 | 103 | 575 | 1.70 | 13.5 | 2379–2412 |
| 4 | 4 | 60.54 | 678 | 101 | 576 | 1.67 | 14.1 | 2379–2412 |

Replaced detection jobs do not erase accepted frames from the bounded temporal
RGB history. These are detection update rates, not video capture or display FPS.
Frame acknowledgements measure local transport only, not time to detect an event.
GPU samples include desktop/other allocations and are sampled every five seconds.
The two-source run was measured after the four-source run in the same service;
caches/warmup can affect timings. Neither is an isolated continuous-operation
thermal/memory benchmark. No accuracy or three-second alert-delay gate is passed.

Start with two test sources for further engineering validation. Four sources
already reduce track updates to about 1.7 FPS; do not claim four crowded rooms
are covered reliably. More representative data and hardware/model profiling are
required before selecting a production configuration.

Raw reports: `runs/two-camera-final.json`, `runs/four-camera-final.json` (ignored).
Runner: `../benchmark_classrooms.py`; requires an explicitly disposable metadata
store and refuses to replace non-QA cameras. No credentials or frames are saved
in the compact report.
