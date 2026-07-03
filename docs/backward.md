# Backward Simulations

## Scientific Scope

This document describes backward source-estimation workflows as screening tools grounded in receptor-footprint and Lagrangian inverse-transport literature. The emphasis is on traceable assumptions, deterministic configuration, and transparent uncertainty limits.

Backward simulation estimates where an observed plume, odor episode, smoke trace, or fire may have originated. It is a screening and attribution aid, not proof of source identity.

## Plume Source Attribution

Spritz supports two backward plume estimators:

- `gaussian`: a steady adjoint-style footprint. Each observed receptor projects upwind through the mean SpritzMet wind field. Candidate cells receive likelihood when they are upwind and close to the crosswind footprint.
- `particles`: a backward residence histogram. Particles are released from observation points and transported against the mean wind with stochastic horizontal spread.

Both methods use the same `receptors` block as observation points. Optional `run.observations` weights detections:

```json
{
  "run": {
    "observations": {"odor-1": 1.0, "odor-2": 0.7},
    "backward_sigma_cross_m": 300.0,
    "backward_particles": 5000,
    "backward_duration_s": 3600
  }
}
```

Run:

```bash
spritzmet --config examples/backward_plume.json --output output_backward/meteo.json --format json
sprtz-backward --config examples/backward_plume.json --meteo output_backward/meteo.json --model gaussian --output output_backward/source_likelihood.json
sprtz-backward --config examples/backward_plume.json --meteo output_backward/meteo.json --model particles --output output_backward/source_likelihood.csv --format csv
```

The output contains `source_likelihood[y,x]`, normalized so the grid sum is 1 when at least one candidate cell is plausible.

## Firefront Origin Attribution

SpritzFire backward simulation estimates likely ignition cells from observed burned/fire points. Observations are supplied as `fire.ignitions` with `row` and `col`; for backward mode these are interpreted as observed fire points, not asserted ignition origins.

```bash
sprtz-backward --config examples/backward_firefront.json --model firefront --output output_backward_fire/ignition_likelihood.json
```

The output contains `ignition_likelihood[y,x]`. The current clean-room estimator favors upwind cells that could plausibly reach observed burned points under an anisotropic spread footprint.

## Interpretation

Use backward outputs as ranked candidate maps. Review the highest-likelihood cells against terrain, land cover, incident reports, time stamps, and independent observations. Do not use backward likelihood as legal or regulatory proof without external validation.

## Limitations

- Mean wind is used by the current plume estimators.
- Chemical transformation and source intermittency are not inferred.
- Firefront backward mode is a screening footprint, not a full inverse stochastic CA calibration.
- Multiple source events can create ambiguous likelihood maps.

## References

- Lin, J. C., Gerbig, C., Wofsy, S. C., Andrews, A. E., Daube, B. C., Davis, K. J., and Grainger, C. A. (2003). A near-field tool for simulating the upstream influence of atmospheric observations: the Stochastic Time-Inverted Lagrangian Transport model. Journal of Geophysical Research: Atmospheres, 108(D16), 4493.
- Seibert, P., and Frank, A. (2004). Source-receptor matrix calculation with a Lagrangian particle dispersion model in backward mode. Atmospheric Chemistry and Physics, 4, 51-63.
- Weil, J. C., Sykes, R. I., and Venkatram, A. (1992). Evaluating air-quality models: review and outlook. Journal of Applied Meteorology, 31(10), 1121-1145.
- Draxler, R. R., and Hess, G. D. (1998). An overview of the HYSPLIT_4 modelling system for trajectories, dispersion, and deposition. Australian Meteorological Magazine, 47(4), 295-308.
- Stohl, A., Forster, C., Frank, A., Seibert, P., and Wotawa, G. (2005). Technical note: The Lagrangian particle dispersion model FLEXPART version 6.2. Atmospheric Chemistry and Physics, 5, 2461-2474.
