"""Synthetic data builders for tests and the ops drills (dev / test only, never imported by product code).

02.8 (REV-0275): moved out of ``platform_core.tests`` so that ``ops/backup/drill_seed.py`` does not import the
test package. Everything here builds SYNTHETIC, labelled data («محیط آزمایشی — داده ساختگی»): no real people,
customers, codes or network ranges. Product code under ``platform_core`` must not import this package; the
pytest fixtures stay in ``platform_core.tests``.
"""
