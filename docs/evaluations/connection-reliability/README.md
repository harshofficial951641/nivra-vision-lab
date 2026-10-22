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
