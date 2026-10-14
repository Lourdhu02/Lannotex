# Performance baseline protocol

No performance claim has been made for v0.0.2. Measure on target hardware using a
representative 10 GB image folder and record: cold startup, time to first image,
mean/P95 image switch, images/minute imported, and process private memory after
1,000 navigations.

As of v0.0.2, folder import reads image dimensions synchronously, so it is **not**
appropriate for large datasets; this document deliberately records the limitation
rather than claiming a benchmark. The v0.1 background importer (see
`ROADMAP.md`) is the planned fix. `lannotex analyze <project>` can be used from the
CLI to reproduce dataset-level validation costs headlessly.
