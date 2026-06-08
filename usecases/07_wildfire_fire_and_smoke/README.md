# Use Case 07: Wildfire Fire And Smoke

Demonstrates the documented `fire+puff` workflow: fire spread outputs are generated first, then the standard Spritz puff workflow can be run on the same configuration.

```bash
sprtz run examples/wildfire_minimal.json --backend fire+puff --output-dir output_fire_smoke --interchange json
```
