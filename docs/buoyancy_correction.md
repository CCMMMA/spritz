# SpritzFire Semi-coupled Buoyancy Wind Correction

## Physical Basis

Large fires can create pyroconvective updraft and near-surface inflow. Sprtz applies this as one-way fire-to-wind post-processing.

## Algorithm

Cells above the fire probability threshold receive wind-speed reduction in the core. Nearby perimeter cells receive wind-speed enhancement. Wind direction is unchanged.

## Configuration

Use `BuoyancyConfig` under `fire.buoyancy`.
