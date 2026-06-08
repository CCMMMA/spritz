# SpritzFire NetCDF-CF Output

`firefront.nc` follows a compact CF-1.8 layout with `time`, `x`, `y`, optional `lat`/`lon`, `fire_probability(time,y,x)`, `arrival_time(y,x)`, and `intensity(time,y,x)`.

When `netCDF4` is not installed, Sprtz writes a JSON fallback with the same logical fields.
