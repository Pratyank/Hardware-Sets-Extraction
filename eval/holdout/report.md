# Evaluation report

Documents: 2

## Totals

| metric | micro | macro |
|---|---|---|
| set recall | 100.0% | 100.0% |
| set precision | 100.0% | 100.0% |
| set F1 | 100.0% | 100.0% |
| not_used status accuracy | 100.0% | - |
| component recall | 99.9% | - |
| component precision | 100.0% | - |
| component F1 | 99.9% | - |
| location IoU (mean) | 0.929 | 0.939 |
| set_fully_correct | 94.4% | 93.4% |

Sets: 107 gold, 107 predicted, 107 matched (0 by IoU fallback). Components (in matched sets): 821 gold, 820 predicted, 820 matched.

## Per book

| doc | pages | gold | pred | matched | R | P | F1 | status | comp R | comp P | mfr | finish | qty | loc IoU | fully correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 418-445 | 39 | 39 | 39 | 100.0% | 100.0% | 100.0% | 100.0% | 99.7% | 100.0% | 99.7% | 100.0% | 99.7% | 0.975 | 89.7% |
| livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1 | 643-662 | 68 | 68 | 68 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.903 | 97.1% |

## Field accuracy (matched components)

| field | correct/total | exact | fuzzy |
|---|---|---|---|
| qty | 819/820 | 99.9% | - |
| qty_unit | 818/820 | 99.8% | - |
| description | 815/820 | 99.4% | 0.999 |
| catalog_number | 813/820 | 99.1% | 0.997 |
| mfr | 819/820 | 99.9% | - |
| finish | 820/820 | 100.0% | - |
| notes | 820/820 | 100.0% | - |

## Manufacturer vs finish confusion

Rows: the role of a gold code. Columns: where that code landed in the prediction (`missing` = absent or a different value).

| gold \ pred | mfr | finish | other | missing |
|---|---|---|---|---|
| mfr | 813 | 0 | 0 | 0 |
| finish | 0 | 654 | 0 | 0 |

## Reliability (predicted field confidence vs exact accuracy)

| bucket | count | accuracy |
|---|---|---|
| [0.0, 0.2) | 0 | - |
| [0.2, 0.4) | 0 | - |
| [0.4, 0.6) | 0 | - |
| [0.6, 0.8) | 0 | - |
| [0.8, 0.9) | 27 | 81.5% |
| [0.9, 1.0] | 4893 | 99.8% |

## 10 worst errors

| # | kind | doc | set | page | line | field | gold | pred | link |
|---|---|---|---|---|---|---|---|---|---|
| 1 | wrong_mfr | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | mfr | ∅ | ZER | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 2 | wrong_qty | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | qty | ∅ | 1 | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 3 | wrong_field | livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1 | 17.0 | 647 | L647_14 | catalog_number | LP200A 6' | LP200A | [open](http://localhost:8000/#doc=livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1&set=16) |
| 4 | wrong_field | livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1 | 18.0 | 647 | L647_19 | catalog_number | LP200A 6' | LP200A | [open](http://localhost:8000/#doc=livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1&set=17) |
| 5 | missed_component | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | ∅ | ∅ | ∅ | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 6 | wrong_field | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | catalog_number | BY DOOR / FRAME MANUFACTURER | 139N PSA BY DOOR / FRAME MANUFACTURER | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 7 | wrong_field | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | catalog_number | PS906 900-4RL 900-2RS 900-BBK 120/240 VAC | PS906 900-4RL 900-2RS 900-BBK 120/240 VAC FURNISH ADDITIONAL PIVOTS AS REQUIRED FOR DOORS 7'6" AND OVER | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 8 | wrong_field | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | description | SEALS - AS TESTED BY DOOR MANUFACTURER | MULLION SEAL SEALS - AS TESTED BY DOOR MANUFACTURER | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 9 | wrong_field | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | description | POWER SUPPLY | POWER SUPPLY NOTE | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
| 10 | wrong_field | village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 02 | 418 | L418_2 | qty_unit | ∅ | EA | [open](http://localhost:8000/#doc=village-of-oswego-new-public-works-facility-copy--specifications-volume-1&set=0) |
