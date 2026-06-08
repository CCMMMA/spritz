# SpritzFire Numerical Methods

## Cellular Automaton

Spread uses a Moore neighborhood. Transition probability is the nominal 7-class fuel probability multiplied by named wind, slope, and fine-fuel-moisture factors, then clamped to `[0, 1]`.

## Rate Of Spread

Nominal ROS is adjusted by the same modifiers. Transition time is cell distance divided by ROS, with diagonal moves using `sqrt(2) * dx`.

## Byram Intensity

Byram fireline intensity is computed from available fuel load, heat of combustion, moisture, and ROS.

## RandomFront Spotting

Firebrand landing distance follows a lognormal distribution. The location parameter derives from intensity, wind speed at ABL top, ABL height, firebrand radius, and settling velocity. The 99.5th percentile defines the characteristic maximum spotting distance.

## Buoyancy Correction

Semi-coupled buoyancy uses Byram convective number. Wind-driven fires below `N_c=2` are unchanged; plume-dominated fires above `N_c=10` receive full core updraft reduction and perimeter inflow enhancement.
