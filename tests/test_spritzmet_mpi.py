from sprtz.models.spritzmet_mpi import _balanced_decomposition, local_slice


def test_balanced_decomposition_product_equals_size():
    for n in [1, 2, 4, 6, 8, 12, 16]:
        py, px = _balanced_decomposition(200, 120, n)
        assert py * px == n


def test_local_slices_cover_full_domain():
    ny, nx, py, px = 11, 13, 3, 2
    area = 0
    for cy in range(py):
        for cx in range(px):
            ly, lx, oy, ox = local_slice(ny, nx, py, px, cy, cx)
            assert 0 <= oy < ny and 0 <= ox < nx
            area += ly * lx
    assert area == ny * nx
