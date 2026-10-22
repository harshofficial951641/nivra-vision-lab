# Website connection reliability

The user chose to fix the website connection first and keep internet access for this release. This is not an offline browser setup.

The failure was below the camera model. During investigation the public homepage returned 200 in about half a second while the public API timed out. The Mac application and its local gateway responded in milliseconds; an independent internet control was reachable. The Quick Tunnel still resolved in DNS, but its HTTPS route stopped responding. The previous DNS-only monitor did not detect this state.

Changes in this release:

- Check the tunnel's actual application response every 20 seconds. Recover after three consecutive failures only while the local gateway and independent internet control remain reachable. Each probe has a hard process deadline, no owner/device cookie, and no surviving DNS worker. Existing restart limits remain in place.
- Bound the Vercel upstream request to eight seconds, before the browser's twelve-second ticket deadline. Cancel upstream requests when the browser disconnects. Do not retry mutating requests automatically.
- Cancel abandoned browser ticket attempts. Give the WebSocket handshake its own deadline after the ticket request completes.
- Keep recently healthy wall and guard connections when a tab becomes visible or the browser reports a network change. Recover a silent wall connection after fifteen seconds without an authenticated snapshot.
- Use real connection outcomes instead of blocking attempts based on `navigator.onLine`. Browser network hints are [not a reliable reachability check](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/onLine).
- Keep the bounded eight-frame camera window during brief acknowledgement stalls; reconnect after eight seconds rather than three. Slow viewers get a two-second send budget while old preview work is still discarded.
- Keep the phone's detector and capture running across transport retries. Send cached detection status to the replacement connection before fresh reports. Stop and pairing revocation still release capture and analysis.

The original skeleton model and decision rules are unchanged. Detection accuracy and connection reliability are separate checks.

Public browser verification uses a private temporary workspace, synthetic moving canvas media, the actual deployed JavaScript, real socket tickets, WebSocket transport and frame acknowledgements. It tests sixty seconds of continuous streaming and three forced camera/wall connection interruptions. It does not measure a physical iPhone, multiple-phone throughput, or fight-detection accuracy. The fixture's owner, camera and guard sessions are isolated from existing user cookies; its workspace is deleted afterward. Raw credentials and screenshots stay in ignored local test results. Final metadata is recorded after the live test.


## Public verification on 23 October 2026

The deployed release `50f92f0` passed the real public-browser test. In sixty seconds the camera added 604 acknowledged frames and the wall received 607 additional preview packets. Camera and wall each kept one open connection with zero closes and an unchanged camera generation. Server analysis advanced from zero to 148 completed reports during that interval.

| Deliberate camera and wall disconnect | Automatic recovery |
|---|---:|
| 1 | 2.694 seconds |
| 2 | 3.184 seconds |
| 3 | 2.132 seconds |

Fresh analysis reports and live wall previews resumed after all three interruptions without another QR scan or Start action. The Full model was fetched once across the entire run. A guard tab's visibility event preserved its healthy socket. The temporary QA workspace was deleted with HTTP 204; its private credential backup was removed and the test browser closed.

The release passed 617 web tests, 156 backend tests, five relay HTTP tests, lint and the production build. Public JavaScript was checked against the tested local build byte for byte. [Sanitized result metadata](public-results.json) records the exact boundary and limitations. These figures describe this browser test, not physical iPhone performance or a guarantee for every network.

To reproduce, run `NIVRA_QA_RELEASE_READY=1 node scripts/evaluation/public-reliability/run.cjs` from the repository root after a release is ready. It creates and deletes only its own temporary workspace. Private browser state and screenshots are written under ignored `test-results/public-reliability-qa`.
