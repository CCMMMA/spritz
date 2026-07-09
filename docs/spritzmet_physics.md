# Optional SpritzMet physics operators

SpritzMet provides independently testable physical operators in
`sprtz.models.spritzmet_physics`. They extend the deterministic workflow
without changing default output. No operator is enabled unless the caller
supplies `physics_options`.

## Thermodynamic operators

`correct_temperature` applies \(T_2=T_1-\Gamma(z_2-z_1)\). The lapse rate can
be constant, a bounded function of bulk Richardson number, or a configurable
moist approximation. `hypsometric_pressure` then reconstructs pressure as
\(p_2=p_1\exp[-g(z_2-z_1)/(R_d\bar T)]\).

Humidity helpers convert relative humidity to vapour pressure before a
temperature change and reconstruct bounded relative humidity afterward. This
preserves vapour pressure except where saturation requires clipping. These
functions are public building blocks; existing WRF downscaling retains its
established lapse-rate behaviour for backward compatibility.

## Wind operator sequence

Existing terrain and roughness corrections run first. The optional stages are
bounded bulk-Richardson stability scaling, horizontal diagnostic divergence
minimization, and quality-control diagnostics.

```python
met = downscale_wrf_to_local_grid(
    wrf,
    center_lat=40.8,
    center_lon=14.2,
    physics_options={
        "wind": {
            "stability": {"bulk_richardson_number": 0.15},
            "mass_consistency": {"iterations": 80, "relaxation": 0.8},
        }
    },
)
```

The projection solves a velocity-potential Poisson problem with bounded Jacobi
iteration and zero-gradient boundaries. It is not a full three-dimensional
anelastic solver and does not reconstruct vertical velocity.

Cost is proportional to `time × levels × rows × columns × iterations`. The
boundary treatment is local to each MPI partition; use serial execution for
validation-quality projected fields until a halo-coupled solver is available.

## Validation

`field_metrics` reports RMSE, MAE, and bias. `wind_metrics` reports vector RMSE
and wrapped wind-direction MAE. Validation should stratify observations by
flat, coastal, valley, urban, stable, unstable, strong-wind, and weak-wind
conditions. Divergence RMS before and after projection is included in metadata.
Operational claims require evaluation against independent observations.

## References

- Sherman, C. A. (1978). A mass-consistent model for wind fields over complex
  terrain. *Journal of Applied Meteorology*, 17(3), 312–319.
- Jiménez, P. A., Dudhia, J., González-Rouco, J. F., et al. (2012). A revised
  scheme for the WRF surface layer formulation. *Monthly Weather Review*, 140,
  898–918.
- Rotach, M. W., et al. (2014). Challenges in complex terrain atmospheric
  modelling. *Meteorologische Zeitschrift*, 23, 487–503.
