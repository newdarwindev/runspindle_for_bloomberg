# Source asset guide

All files in [`assets/`](assets/) are original inputs. The [site](src/index.html) is built from these files and exposes the SHA-256, size, description, and related records in generated `asset-catalog.json`. Links below use repository paths; the published site copies the originals for direct download.

| File | Annotation and relationship |
| --- | --- |
| [Product concept PDF](assets/runspindle_bloomberg_product.pdf) | 16-page presentation for the Bloomberg Terminal concept. Summarizes the two workflow modes and selected cases from the [40-case CSV](assets/runspindle_bloomberg_workflows.csv); the [ranked CSV](assets/runspindle_bloomberg_ranked.csv) adds prioritization. |
| [Workflow CSV](assets/runspindle_bloomberg_workflows.csv) | Canonical 40 full scenarios: eight cross-system business workflows and 32 Terminal-only paper workflows. Includes the Terminal check, action or pause, verification, alternatives, assumptions and supporting URLs. The [product PDF](assets/runspindle_bloomberg_product.pdf) is its presentation layer. |
| [Ranked CSV](assets/runspindle_bloomberg_ranked.csv) | Reorders the same 40 IDs and adds priority scores and rationale. Scores are supplied judgments, not measured outcomes. Join to the [workflow CSV](assets/runspindle_bloomberg_workflows.csv) on `example_id`. |
| [Research paper](assets/runspindle-paper.pdf) | 12-page *Testing Maintained Workflows Under Explicit Authority* proposal. Defines accepted completion, human intervention and evaluation questions; states that the integrated system is unimplemented. The [exact paper package](assets/runspindle-paper-exact-v5.zip) carries this PDF and a checksum manifest. |
| [Exact paper package](assets/runspindle-paper-exact-v5.zip) | Two-file ZIP containing `runspindle-paper.pdf` and `manifest.json`. The manifest identifies the paper by SHA-256 and byte count. |
| [Original UI gallery](assets/Runspindle-UI-gallery.pdf) | 29-page raster-only conceptual UI presentation. Its sequence is represented by the 29 named PNGs in the [illustrations archive](assets/Runspindle-UI-illustrations.zip) and retained in the first 29 pages of the [revised gallery](assets/Runspindle_Revised_Gallery.pdf). |
| [UI illustrations archive](assets/Runspindle-UI-illustrations.zip) | 29 named PNGs and `INDEX.txt` for the original gallery sequence. Use the [original PDF](assets/Runspindle-UI-gallery.pdf) for page context. |
| [Revised gallery PDF](assets/Runspindle_Revised_Gallery.pdf) | 37-page Pet Tabletop presentation: 29 original-slide compositions plus eight additional fictional Bloomberg business cases. The [page/source index](assets/Runspindle_Gallery_Index.html) maps all 37 pages; the [PNG archive](assets/Runspindle_Gallery_37_PNGs.zip) provides page images. |
| [Gallery page/source index](assets/Runspindle_Gallery_Index.html) | HTML map of 37 pages and official citations for the eight additional cases. It explicitly states which records are synthetic and where source UI was retained. |
| [Gallery PNG archive](assets/Runspindle_Gallery_37_PNGs.zip) | 37 full-size page images in the same order as the [revised PDF](assets/Runspindle_Revised_Gallery.pdf). The website derives compressed previews from these images. |
| [Duplicate gallery PNG archive](<assets/Runspindle_Gallery_37_PNGs (1).zip>) | Byte-identical second copy of the 37-image archive (`e83ff522…40ae2c08a0f`). Retained as supplied and linked to its canonical twin above. |

## Provenance and claim boundaries

The Bloomberg workflows use fictional businesses and synthetic values. Their Terminal commands and market conventions are linked to sources in the CSV fields; the source URLs are included for review, not as proof of an operating integration. The product PDF is a concept, and the research paper does not report live acceptance, measured savings or deployed Runspindle software. The gallery index marks its eight added cases as proposed workflows. Keep those distinctions in derivative marketing or publication.
