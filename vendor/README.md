# kordoc local rendering patch

Upstream: https://github.com/chrisryugj/kordoc, tag v4.25.20,
commit 9fb8a105d67afd394f0930716075302e37d137ea (MIT).
Local package: 4.25.20-upmu.1; not an upstream release.

Fixes ruby/dutmal placement and pagination, SVG whitespace, Human Myeongjo
bold in HTML, duplicate PDF text from synthetic strokes, and thin DASH borders.
Only a locally installed Windows HMKMM.TTF is read at runtime. No proprietary
font file is distributed. Generated HTML previews contain that local font and
are local cache files, not public release assets.

Rebuild: check out the commit, apply the .patch, copy local-font.ts to
src/render/local-font.ts, set package version to 4.25.20-upmu.1, npm ci,
npm run build, npm pack --ignore-scripts. The tarball is pinned by package-lock.
Use HTML preview to retain the explicit font face; standalone SVG is not equivalent.

Validation on the development PC: 4 documents / 9 pages; matching page count,
per-page characters and normalized line breaks; max baseline delta 0.085pt.
This is not a claim of pixel-identical rendering for arbitrary HWPX or other PCs.
Optional native Hancom verification remains available.
