# Publishing-quality visualization

`sprtz.models.visualization` provides figure generation for suite outputs. The first production function is a receptor concentration scatter plot with equal aspect ratio, labelled axes, colorbar, grid, high DPI output, and support for CSV or NetCDF-CF concentration inputs.

Install visualization dependencies:

```bash
python -m pip install -e .[viz]
```

Create a figure:

```bash
sprtz-plot --input output/concentration.nc --output output/concentration.png --title "Scenario A" --dpi 600
```

The module imports Matplotlib lazily, so compute-only deployments do not need plotting dependencies.
