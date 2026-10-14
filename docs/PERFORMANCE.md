# Measured desktop baseline — 2026-10-14

Hardware: AMD Ryzen 9 8940HX, approximately 23 GiB usable RAM, Windows 11 build
26300, Python 3.11.9. GPU is not used for these operations. Synthetic files are
generated in a temporary directory by `scripts/benchmark.py` and removed afterward.

| Measurement | Result |
| --- | ---: |
| Main window construction through first processed paint | 86.97 ms |
| Imported JPEG files | 300 |
| Total source bytes | 403,689,900 (~385 MiB) |
| Import time (metadata + verification + SQLite batches) | 1.070 s |
| Import throughput | 280.5 images/s |
| 1920×1080 decode median, 30 samples | 22.24 ms |
| Decode P95 (29th sorted sample) | 25.03 ms |
| Metadata records inserted + paged through | 100,300 |
| Metadata insertion + scrolling | 1.530 s |
| Metadata pages retained | 8 |
| Metadata records retained | 972 (maximum 1,024) |
| Process working set before metadata exercise | 76.13 MiB |
| Process working set after metadata exercise | 81.03 MiB |

Window construction excludes interpreter/Qt imports. Decode timing measures worker
work, not full click-to-display latency or a cold disk. The 300 JPEGs are copies of
one synthetic noisy image, so cache effects matter. The additional 100,000 records
are explicitly metadata-only fixtures; they are not 100,000 real decoded images.
Working set is measured with Windows GetProcessMemoryInfo, not private bytes.

Imports and exports run outside the UI thread. The list is virtualized with an
eight-page metadata cache; decoded preview cache has a 96 MiB budget and serial
decoding. There is no claim of a measured 10 GB real dataset, cold startup, clean-VM
performance, or cross-machine sync latency. Those require representative user data
and the target network. No comparative ranking is claimed.

Reproduce from the repository with `python scripts/benchmark.py` after installing
the package. The script reports hardware/runtime and raw metrics as JSON.
