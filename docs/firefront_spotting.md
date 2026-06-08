# SpritzFire Fire Spotting - RandomFront 2.3

## Overview

RandomFront spotting is implemented as a post-processing step after each cellular-automaton timestep.

## Physical Model

Firebrand landing distance is sampled from a lognormal distribution. Azimuth is biased toward the wind direction.

## Parameterization

The lognormal location parameter is derived from Byram intensity, ABL height, wind speed, firebrand radius, and terminal settling velocity.

## Configuration

Use `SpottingConfig` under `fire.spotting_config` and set `fire.spotting=true`.

## Limitations

The current implementation uses uniform shape parameter sigma and does not model full vertical wind profiles.

## References

Trucchia et al. 2019; Egorova 2020; Lopez-De-Castro 2024.
