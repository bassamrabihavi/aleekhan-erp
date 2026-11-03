"""pytest root config. DB settings come from the environment (PG* or DATABASE_URL); see .env.example."""

from hypothesis import settings

# Property tests are reproducible in CI: derandomized (fixed seed per test), no example database on disk,
# no per-example deadline (Windows/CI timing noise must not cause flaky failures).
settings.register_profile("aleekhan", derandomize=True, database=None, deadline=None, max_examples=200)
settings.load_profile("aleekhan")
