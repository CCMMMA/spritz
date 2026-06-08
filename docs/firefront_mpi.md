# SpritzFire MPI

SpritzFire MPI splits stochastic realizations across ranks. Each rank runs independent realizations with a rank-offset seed and rank 0 reduces ensemble probability and arrival time.

```bash
mpiexec -n 4 sprtzfire --config examples/wildfire_mpi.json --output-dir output_fire_mpi --parallel mpi
```

MPI remains optional and requires `mpi4py`.
