# Earlier endpoint-only cache defect

The user tested candidate5591bb4 on a camera. Endpoint edits were stored, but the image changed only after a native shadow edit. The native retained updater604b3034 and comparator604b2d78 reproduce the cause: they do not compare the new job endpoint word. With unchanged native controls the comparator returns0xc0000000, outside the tone-change mask0x02e8063e. The previous endpoint adapter obeyed that mask and reused the old LUT. Its neutral shortcut also reused a previously modified curve when resetting endpoints.

The current adapter still rebuilds every supported tagged ordinary COLOR request,
including neutral reset. The native legacy-only zero gate is preserved, while
the old H/M/L overlay is now replaced by the equal-quarter transfer. No retained
state or forged dirty bit was added. Probe instruction counts describe fixture
work, not elapsed camera time.

`cached_endpoint_cases` still executes the actual retained updater/comparator,
then two canonical changes and reset with unchanged native controls. Its24
transitions cover zero/nonzero captured H/M/L, selected/override bases and both
variants, including the production entry. The full LUT must equal a fresh native
legacy-only baseline followed by the shared map; neutral pointer/return must
match that baseline. No function is modeled.

The current native footer publishes real selected values together with the next
INFO destination. It retains the Japanese endpoint name and native INFO icon,
using the same inline descriptor format. The former custom numeric paint row
is removed. Publication, native query compaction and formatting contracts are
in [TONE_GRAPH.md](TONE_GRAPH.md). This meaningful-payload change has bounded
native verification but no physical LCD or async-delivery qualification.

## Later white-only report

After candidate6ebce6d, the user reported that white edits appeared only after
changing highlight, while black edits worked immediately. The current change
restores the physical front dial to white and rear dial to black; it does not
claim a fix for the white-only refresh report.

The bounded comparison has not reproduced a black/white asymmetry. Actual
binding and all eight native input continuations across COLOR1–3 commit the
canonical word, publish the source, set the changed flag, return1 and enter the
outer viewer. Eight COLOR1 cases continue through the whole native viewer:
parameter118 contains the changed B/W text with notify1, the native store copies
92 bytes, the observer pending bit is set and event6400 is prepared. These cases
bypass the unchanged GUI logging/busy-check envelope and model profile-refresh,
application-state and settings-notification completion; event-queue submission
and delivery remain outside the fixture. They do not prove visible refresh.

Independent strict probes retain all32 source bits through white-only changes
and acquisition. The native builder and both upload banks also accept white-only
changes with unchanged native controls. Upload locks are modeled. These separate
fixtures do not establish the scheduling of a real camera transaction.

The recorded evidence is under `generated/tone-curve/white-refresh/`:
`callback-continuation.json`, `viewer-publication.json`,
`review-publication.json`, `review-refresh-prefix.json`,
`image-isolation-v2/audit.json` and `image-sequence.json`, with the corresponding
rerunnable scripts. Physical display/liveview behavior remains unverified here;
no additional refresh flag or invalidation was added without a reproduced cause.
