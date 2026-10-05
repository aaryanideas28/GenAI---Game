"""Unit tests for world reset and spawn protection."""

from types import SimpleNamespace
from game.world import World, MIN_WRAP_Z, CHUNK_LEN, NUM_CHUNKS


def test_world_reset_positions():
    """Verify that World.reset() properly restores track chunks and tunnel positions."""
    w = object.__new__(World)
    w.chunks = [SimpleNamespace(z=0.0) for _ in range(NUM_CHUNKS)]
    w.tunnels = [
        SimpleNamespace(z=0.0, x=0.0, scale_x=1.0, tunnel_lane=-1),
        SimpleNamespace(z=0.0, x=0.0, scale_x=1.0, tunnel_lane=-1),
    ]

    w.reset()

    # Track chunks reset
    for i, c in enumerate(w.chunks):
        assert c.z == MIN_WRAP_Z + i * CHUNK_LEN

    # Tunnels pushed back far down the track away from Jake (z=0)
    assert [t.z for t in w.tunnels] == [160.0, 360.0]
    for t in w.tunnels:
        assert t.tunnel_lane in (-1, 0, 1)


def test_world_reset_fallback_chunks():
    """Verify that fallback chunks (not equal to NUM_CHUNKS) reset to z=120.0."""
    w = object.__new__(World)
    w.chunks = [SimpleNamespace(z=-10.0), SimpleNamespace(z=-20.0), SimpleNamespace(z=-30.0)]
    w.tunnels = []

    w.reset()

    for c in w.chunks:
        assert c.z == 120.0
