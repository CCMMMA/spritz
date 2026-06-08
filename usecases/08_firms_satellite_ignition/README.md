# Use Case 08: FIRMS Satellite Ignition

Uses NASA FIRMS/VIIRS detections as ignition points. Network access is explicit and requires `FIRMS_MAP_KEY`.

```bash
FIRMS_MAP_KEY=... sprtzfire --firms --config examples/wildfire_minimal.json --output-dir output_firms --interchange json
```
