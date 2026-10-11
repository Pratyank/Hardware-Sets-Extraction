# Evaluation report

Documents: 8

## Totals

| metric | micro | macro |
|---|---|---|
| set recall | 100.0% | 100.0% |
| set precision | 99.3% | 99.5% |
| set F1 | 99.6% | 99.8% |
| not_used status accuracy | 99.6% | - |
| component recall | 99.3% | - |
| component precision | 99.7% | - |
| component F1 | 99.5% | - |
| location IoU (mean) | 0.919 | 0.929 |
| set_fully_correct | 91.4% | 90.8% |

Sets: 279 gold, 281 predicted, 279 matched (0 by IoU fallback). Components (in matched sets): 2184 gold, 2174 predicted, 2168 matched.

## Per book

| doc | pages | gold | pred | matched | R | P | F1 | status | comp R | comp P | mfr | finish | qty | loc IoU | fully correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| valor-acres-building-e--087100-door-hardware-rev-2 | 7-18 | 37 | 37 | 37 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 99.6% | 100.0% | 100.0% | 100.0% | 0.976 | 94.6% |
| roselle-public-library--087100-fl-door-hardware-ifb-revised | 15-17 | 33 | 33 | 33 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 99.5% | 100.0% | 100.0% | 0.925 | 75.8% |
| jc-ryan-2--087100-door-hardware-6 | 24-46 | 38 | 38 | 38 | 100.0% | 100.0% | 100.0% | 100.0% | 99.6% | 100.0% | 100.0% | 100.0% | 100.0% | 0.933 | 97.4% |
| 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 19-36 | 35 | 35 | 35 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.970 | 91.4% |
| lyons-township-hs--project-manual-1 | 285-294 | 29 | 29 | 29 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.974 | 100.0% |
| hfh-dg-hospital--08-71-00-door-hardware | 20-40 | 25 | 25 | 25 | 100.0% | 100.0% | 100.0% | 100.0% | 99.7% | 99.4% | 100.0% | 100.0% | 99.4% | 0.961 | 84.0% |
| 81-85-bridgeport--08-70-00-hardware-schedule | 3-18 | 31 | 31 | 31 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 98.9% | 100.0% | 100.0% | 100.0% | 0.909 | 87.1% |
| sjc-well-behavioral--89671ede-20260218-sjc-bewell-bldg-b-85-design-update-specifications | 711-724 | 51 | 53 | 51 | 100.0% | 96.2% | 98.1% | 98.0% | 94.4% | 100.0% | 100.0% | 100.0% | 100.0% | 0.781 | 96.1% |

## Field accuracy (matched components)

| field | correct/total | exact | fuzzy |
|---|---|---|---|
| qty | 2166/2168 | 99.9% | - |
| qty_unit | 2168/2168 | 100.0% | - |
| description | 2159/2168 | 99.6% | 0.999 |
| catalog_number | 2161/2168 | 99.7% | 0.999 |
| mfr | 2167/2168 | 100.0% | - |
| finish | 2168/2168 | 100.0% | - |
| notes | 2154/2168 | 99.4% | - |

## Manufacturer vs finish confusion

Rows: the role of a gold code. Columns: where that code landed in the prediction (`missing` = absent or a different value).

| gold \ pred | mfr | finish | other | missing |
|---|---|---|---|---|
| mfr | 1482 | 0 | 1 | 0 |
| finish | 0 | 1546 | 0 | 0 |

## Reliability (predicted field confidence vs exact accuracy)

| bucket | count | accuracy |
|---|---|---|
| [0.0, 0.2) | 0 | - |
| [0.2, 0.4) | 0 | - |
| [0.4, 0.6) | 0 | - |
| [0.6, 0.8) | 0 | - |
| [0.8, 0.9) | 124 | 98.4% |
| [0.9, 1.0] | 12884 | 99.8% |

## 10 worst errors

| # | kind | doc | set | page | line | field | gold | pred | link |
|---|---|---|---|---|---|---|---|---|---|
| 1 | wrong_mfr | roselle-public-library--087100-fl-door-hardware-ifb-revised | 6.1 | 17 | L17_13 | mfr | TRINE | ∅ | [open](http://localhost:8000/#doc=roselle-public-library--087100-fl-door-hardware-ifb-revised&set=22) |
| 2 | wrong_qty | hfh-dg-hospital--08-71-00-door-hardware | 017 | 31 | L31_40 | qty | 2 | ∅ | [open](http://localhost:8000/#doc=hfh-dg-hospital--08-71-00-door-hardware&set=13) |
| 3 | wrong_qty | hfh-dg-hospital--08-71-00-door-hardware | 017 | 31 | L31_40 | qty | 3 | ∅ | [open](http://localhost:8000/#doc=hfh-dg-hospital--08-71-00-door-hardware&set=13) |
| 4 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | description | Overhead Stop(s) | Overhead Stop(s) Active Leaf | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 5 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | description | Closer(s) | Closer(s) Top Jamb Mount | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 6 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | notes | Active Leaf | ∅ | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 7 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | notes | Top Jamb Mount | ∅ | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 8 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 31 | 34 | L34_18 | description | Push to Lock Button | Push to Lock Button Shared with D147A | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=30) |
| 9 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 31 | 34 | L34_18 | description | Wiring Diagrams | Wiring Diagrams Interlock with D147A. | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=30) |
| 10 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 31 | 34 | L34_18 | notes | Shared with D147A | ∅ | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=30) |
