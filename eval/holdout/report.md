# Evaluation report

Documents: 2

## Totals

| metric | micro | macro |
|---|---|---|
| set recall | 100.0% | 100.0% |
| set precision | 100.0% | 100.0% |
| set F1 | 100.0% | 100.0% |
| not_used status accuracy | 100.0% | - |
| component recall | 100.0% | - |
| component precision | 100.0% | - |
| component F1 | 100.0% | - |
| location IoU (mean) | 0.929 | 0.939 |
| set_fully_correct | 98.1% | 98.5% |

Sets: 107 gold, 107 predicted, 107 matched (0 by IoU fallback). Components (in matched sets): 821 gold, 821 predicted, 821 matched.

## Per book

| doc | pages | gold | pred | matched | R | P | F1 | status | comp R | comp P | mfr | finish | qty | loc IoU | fully correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| village-of-oswego-new-public-works-facility-copy--specifications-volume-1 | 418-445 | 39 | 39 | 39 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.975 | 100.0% |
| livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1 | 643-662 | 68 | 68 | 68 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.903 | 97.1% |

## Field accuracy (matched components)

| field | correct/total | exact | fuzzy |
|---|---|---|---|
| qty | 821/821 | 100.0% | - |
| qty_unit | 821/821 | 100.0% | - |
| description | 821/821 | 100.0% | 1.000 |
| catalog_number | 819/821 | 99.8% | 1.000 |
| mfr | 821/821 | 100.0% | - |
| finish | 821/821 | 100.0% | - |
| notes | 821/821 | 100.0% | - |

## Manufacturer vs finish confusion

Rows: the role of a gold code. Columns: where that code landed in the prediction (`missing` = absent or a different value).

| gold \ pred | mfr | finish | other | missing |
|---|---|---|---|---|
| mfr | 814 | 0 | 0 | 0 |
| finish | 0 | 654 | 0 | 0 |

## Reliability (predicted field confidence vs exact accuracy)

| bucket | count | accuracy |
|---|---|---|
| [0.0, 0.2) | 0 | - |
| [0.2, 0.4) | 0 | - |
| [0.4, 0.6) | 0 | - |
| [0.6, 0.8) | 0 | - |
| [0.8, 0.9) | 0 | - |
| [0.9, 1.0] | 4926 | 100.0% |

## 10 worst errors

| # | kind | doc | set | page | line | field | gold | pred | link |
|---|---|---|---|---|---|---|---|---|---|
| 1 | wrong_field | livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1 | 17.0 | 647 | L647_14 | catalog_number | LP200A 6' | LP200A | [open](http://localhost:8000/#doc=livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1&set=16) |
| 2 | wrong_field | livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1 | 18.0 | 647 | L647_19 | catalog_number | LP200A 6' | LP200A | [open](http://localhost:8000/#doc=livelle-mulholland-life-plan-community--2025-12-12-livelle-bid-set-project-manual-vol1-rev1&set=17) |
