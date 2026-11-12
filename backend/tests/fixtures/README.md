Test fixtures only. These small files are hand-written to exercise parsers and edge cases in CI.
They are **not** real procurement data and are never loaded by the demo or used for training.
Real datasets live under `data/real/` (see `docs/real-data.md`).

`real_notices/` - verbatim text of three real World Bank procurement notices for India (public, from
search.worldbank.org/api/v2/procnotices, fetched 2026-11-12), HTML stripped. Used to test extraction on
real tender phrasing: OP00474853 (millet processing plant SITC), OP00471901 (Gurugram Metro viaduct),
OP00464558 (132 kV GIS substation restoration).
