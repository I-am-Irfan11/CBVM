# HITS transport reference data

GateLog keeps HITS transport references separate from fictional operational buses. The checked-in snapshot contains route numbers, route names, and the bus names shown on the official [HITS Transportation page](https://hindustanuniv.ac.in/facilities/transport/). It records the timetable label shown on that page, **2023–2024**, and is marked `reference_only`. No driver or in-charge personal contact details are copied into the dataset.

The page was inspected on 2026-10-03. Because the published timetable is historical, treat it as a reference for project demonstration only; confirm current route and timing details with HITS before operational use. The checked-in snapshot does not assert current boarding times or destinations. Boarding-point arrays are empty where a verified source row was not included.

`python -m app.database.transport --refresh` fetches the official page, validates the timetable, and atomically replaces the checked-in snapshot. It retries transient fetch or parse failures and leaves the existing snapshot intact when validation fails. Route records are seeded into `transport_routes`; they never create operational bus or vehicle records. Buses link to an official route by route number when a reference exists. Custom operational routes remain explicitly unlinked.
