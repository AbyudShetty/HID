# E4 model latency (this machine; compute only)

{'cpu_threads': 16, 'platform': 'Windows-10-10.0.26300-SP0', 'python': '3.10.0'}

| model | input | threads | p50 ms | p95 ms |
|---|---|---|---|---|
| det_10g | 640 | 1 | 202.37 | 212.01 |
| det_10g | 256 | 1 | 50.83 | 89.75 |
| det_500m | 640 | 1 | 31.59 | 52.1 |
| det_500m | 256 | 1 | 3.92 | 12.01 |
| arcface_w600k_r50 | 112 | 1 | 317.06 | 404.3 |
| arcface_w600k_mbf | 112 | 1 | 15.63 | 20.17 |
| minifasnet_v2 | 80 | 1 | 2.37 | 3.86 |
| minifasnet_v1se | 80 | 1 | 2.64 | 5.69 |
| det_10g | 640 | 2 | 162.6 | 216.28 |
| det_10g | 256 | 2 | 25.4 | 41.3 |
| det_500m | 640 | 2 | 15.3 | 23.75 |
| det_500m | 256 | 2 | 2.32 | 3.24 |
| arcface_w600k_r50 | 112 | 2 | 161.88 | 197.01 |
| arcface_w600k_mbf | 112 | 2 | 8.4 | 13.07 |
| minifasnet_v2 | 80 | 2 | 1.82 | 2.37 |
| minifasnet_v1se | 80 | 2 | 1.87 | 2.89 |
| det_10g | 640 | 4 | 102.51 | 120.29 |
| det_10g | 256 | 4 | 15.86 | 19.84 |
| det_500m | 640 | 4 | 10.48 | 14.2 |
| det_500m | 256 | 4 | 2.36 | 3.33 |
| arcface_w600k_r50 | 112 | 4 | 103.93 | 151.68 |
| arcface_w600k_mbf | 112 | 4 | 5.76 | 7.02 |
| minifasnet_v2 | 80 | 4 | 1.63 | 1.8 |
| minifasnet_v1se | 80 | 4 | 1.69 | 2.41 |

Plan budgets (p95, chosen instance): per-crop work (det@256 + regions) <= 20 ms; keyframe work (det@640 + ArcFace + 2x MiniFASNet) <= 300 ms.
These are a laptop, not the target instance: the E4 decision for AWS is still open.
