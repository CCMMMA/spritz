# Backward Simulations

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
