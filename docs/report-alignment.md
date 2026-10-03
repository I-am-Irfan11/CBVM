# Alignment with the GateLog Design Project Report

The attached report is the GateLog domain and functional specification. The user's pasted implementation request is the actionable work instruction. Editorial statements and claims in the report about prior implementation are not treated as verification evidence or as instructions that override the user's request.

| Report requirement | Current repository implementation |
| --- | --- |
| Vehicle categories and registry | Validated plate registry, edit/deactivate, search, history and unique normalized plate index |
| Capture, YOLO and OCR | Replaceable mock/real adapters, video source abstraction, conservative plate normalization and confidence review; real weights/OCR are external |
| Entry/exit and duplicate protection | UTC movement engine, paired exits, duration, event idempotency, cooldown and one-open-visit index |
| Uncertain and unknown readings | Review queue supports confirm/correct, reject and visitor registration; actions are audited |
| Visitor and trip purpose | Visitor details, expected exit, purpose list, custom Other value and recorded entry |
| Bus operation | Bus registry links to route reference; departures/returns link to campus movement records |
| HITS transport data | Sanitized historical 2023–2024 route identifiers and bus names; reference-only and clearly separate from fictional demo vehicles |
| Security | Cloudflare Access Google identity, verified signed assertions, backend role checks, department scoping, admin account and audit management |
| Operations dashboard and live updates | API-backed dashboard includes cameras, open visits, entry/exit counts, review queue, unknown plates, bus trips and activity; reconnecting WebSocket |
| Camera health | Online/offline and last-frame updates from capture worker; one source configured per process |
| Analytics and export | Date/type/purpose/status filtering, daily/hourly counts, stay averages and real CSV export |
| Audit and retention | Actor and role, action, old/new data, TTL indexes and admin-configurable retention for completed/resolved records |
| Cross-platform startup | Windows batch and macOS shell setup, start, seed and test scripts |

Known implementation boundaries are described in [README](../README.md): no model weights or physical camera are bundled, one configured capture source runs per process, PDF export is not included, and movement locks, WebSocket fan-out and audit writes are not distributed/transactional.
