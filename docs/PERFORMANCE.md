# Performance baseline protocol

No performance claim has been made for v0.0.1. Measure on target hardware using a representative 10 GB image folder: record cold startup, time to first image, mean/P95 image switch, images/minute imported, and process private memory after 1,000 navigations. Current folder import reads image dimensions synchronously, so it is not appropriate for large datasets; this document deliberately records the limitation rather than claiming a benchmark.
