# FIRMS/VIIRS Satellite Ignition Source

## Overview

Sprtz can download NASA FIRMS active-fire CSV data and convert hotspots into SpritzFire ignition points.

## MAP_KEY

Set `FIRMS_MAP_KEY`; keys are never stored in cache names or logged in plaintext.

## Sensors

Supported source strings include VIIRS NOAA-20/21/SNPP and MODIS NRT products accepted by the FIRMS API.

## Filtering And Clustering

`FIRMSConfig` filters by confidence and FRP, then greedily clusters nearby hotspots by configurable distance.

## Usage

```bash
FIRMS_MAP_KEY=... sprtzfire --firms --config examples/wildfire_minimal.json --output-dir output_firms
```
