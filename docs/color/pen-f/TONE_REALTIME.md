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
