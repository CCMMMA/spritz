# FIRMS/VIIRS Satellite Ignition Source

## Scientific Scope

This document describes satellite active-fire detections as ignition or assimilation evidence. It treats FIRMS-style products as uncertain observations with geolocation, timing, cloud, and omission limitations.

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

## References

- Schroeder, W., Oliva, P., Giglio, L., and Csiszar, I. A. (2014). The New VIIRS 375 m active fire detection data product: algorithm description and initial assessment. Remote Sensing of Environment, 143, 85-96. https://doi.org/10.1016/j.rse.2013.12.008
- Giglio, L., Schroeder, W., and Justice, C. O. (2016). The Collection 6 MODIS active fire detection algorithm and fire products. Remote Sensing of Environment, 178, 31-41. https://doi.org/10.1016/j.rse.2016.02.054
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 1: Physical and quasi-physical models. International Journal of Wildland Fire, 18(4), 349-368.
- Sullivan, A. L. (2009). Wildland surface fire spread modelling, 1990-2007. 2: Empirical and quasi-empirical models. International Journal of Wildland Fire, 18(4), 369-386.
- Mandel, J., Beezley, J. D., and Kochanski, A. K. (2011). Coupled atmosphere-wildland fire modeling with WRF-Fire. Geoscientific Model Development, 4, 591-610. https://doi.org/10.5194/gmd-4-591-2011
