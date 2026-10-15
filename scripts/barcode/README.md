# Fingerprint barcode colors

The recording and track pages can draw fingerprint thumbnails as color
barcodes (the Bits/Colors switch). Their job is to make an AcoustID linked
to the wrong recording stand out, while copies of the same audio
(remasters, other encodes, cut or shifted files) look alike.

Each band summarizes about 10 seconds of audio: the 16 Gray-decoded filter
levels, averaged. Three fixed directions turn the summary into a color.
They are the directions in which songs differ most, relative to how much
copies of the same audio from different AcoustIDs differ. The swatch at the
start of each barcode is the color of the whole song. It is averaged over
the audio all matching thumbnails on the page share, so a cut or shifted
copy gets the same swatch.

The code is in `acoustid/web/static/fp.js` (colors, swatches) and
`site.js` (the switch). The constants between the `BEGIN/END
BARCODE_BASIS` markers in `fp.js` come from `fit.py`.

## Refitting

1. Extract training data. This only reads the fingerprint database:

   ```sh
   python scripts/barcode/extract.py -c acoustid.conf -o barcode-data \
       --fingerprints 20000 --recordings 5000
   ```

   This writes `random.jsonl` (random fingerprints) and `recordings.jsonl`
   (recordings with two or more AcoustIDs, with the most submitted
   fingerprint of each, as the recording page shows them). Only the first
   948 frames are kept, the part the thumbnails show.

2. Fit, check the report, and write the constants into `fp.js`. Only numpy
   is needed:

   ```sh
   uv run --with numpy scripts/barcode/fit.py barcode-data \
       --current acoustid/web/static/fp.js
   uv run --with numpy scripts/barcode/fit.py barcode-data \
       --write acoustid/web/static/fp.js
   ```

   `--current` also scores the constants that are in `fp.js` now, so the
   two can be compared on the same held-out recordings. `--window` and
   `--step` (in frames, 8 per second) change the band length.

Fitting with the numbers above takes about an hour and a half on one
core, most of it in finding where same-audio fingerprints overlap.

## Reading the report

Color differences are in OKLab × 100, where about 2 is the smallest
visible difference. The report is computed on half of the recordings,
which are left out of that fit, and then everything is refitted for the
constants.

- **bands / swatch: same audio** are pairs of different AcoustIDs of one
  recording that share audio. These should be small.
- **one cut** is the same, with one of the pair cut to 35–70% of its
  length at a random place, like a short file.
- **unrelated** are pairs of random fingerprints, which is what a mislink
  looks like. These should be large.
- **how often same audio looks closer** is the chance that a same-audio
  pair is closer in color than an unrelated pair.
- **disabled links**: if the data has disabled track–recording links,
  which are mostly wrong ones, it reports how often they look farther
  from the top AcoustID of the page than the enabled ones do.
- **song / mastering variance per axis** is how much each color direction
  varies across songs compared with across copies of the same audio. A low
  one means that color reacts to mastering.

The current constants come from 20,000 random fingerprints and 5,000
recordings, extracted from a streaming replica with the command above.
Fitted on half of the recordings and scored on the other half, same-audio
bands differed by 6.7 and unrelated ones by 22.9, and same audio looked
closer 96.9% of the time. Swatches of a cut copy differed by 4.0 when
aligned on the page, against 5.4 when each covered its whole fingerprint.
Disabled links looked farther from the top AcoustID than enabled ones only
58.9% of the time, probably because many are disabled for reasons the
audio can't show, such as the same audio linked to a duplicate recording.

## Keeping Python and JavaScript in sync

`fit.py` has Python copies of the color code (`rank_color`,
`page_swatches`, `find_offset`, ...) to score the constants. When the
drawing code in `fp.js` changes, change those too. A quick check is to
compute colors for the same fingerprints with both; they should match to
the last digit.
