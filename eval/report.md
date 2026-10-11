# Evaluation report

Documents: 8

## Totals

| metric | micro | macro |
|---|---|---|
| set recall | 100.0% | 100.0% |
| set precision | 100.0% | 100.0% |
| set F1 | 100.0% | 100.0% |
| not_used status accuracy | 100.0% | - |
| component recall | 100.0% | - |
| component precision | 99.9% | - |
| component F1 | 99.9% | - |
| location IoU (mean) | 0.926 | 0.934 |
| set_fully_correct | 96.8% | 96.6% |

Sets: 279 gold, 279 predicted, 279 matched (0 by IoU fallback). Components (in matched sets): 2183 gold, 2185 predicted, 2182 matched.

## Per book

| doc | pages | gold | pred | matched | R | P | F1 | status | comp R | comp P | mfr | finish | qty | loc IoU | fully correct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| valor-acres-building-e--087100-door-hardware-rev-2 | 7-18 | 37 | 37 | 37 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.981 | 100.0% |
| roselle-public-library--087100-fl-door-hardware-ifb-revised | 15-17 | 33 | 33 | 33 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 99.5% | 100.0% | 100.0% | 0.925 | 97.0% |
| jc-ryan-2--087100-door-hardware-6 | 24-46 | 38 | 38 | 38 | 100.0% | 100.0% | 100.0% | 100.0% | 99.6% | 100.0% | 100.0% | 100.0% | 100.0% | 0.933 | 97.4% |
| 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 19-36 | 35 | 35 | 35 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.970 | 91.4% |
| lyons-township-hs--project-manual-1 | 285-294 | 29 | 29 | 29 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.974 | 100.0% |
| hfh-dg-hospital--08-71-00-door-hardware | 20-40 | 25 | 25 | 25 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.961 | 100.0% |
| 81-85-bridgeport--08-70-00-hardware-schedule | 3-18 | 31 | 31 | 31 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 98.9% | 100.0% | 100.0% | 100.0% | 0.909 | 87.1% |
| sjc-well-behavioral--89671ede-20260218-sjc-bewell-bldg-b-85-design-update-specifications | 711-724 | 51 | 51 | 51 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% | 0.815 | 100.0% |

## Field accuracy (matched components)

| field | correct/total | exact | fuzzy |
|---|---|---|---|
| qty | 2182/2182 | 100.0% | - |
| qty_unit | 2182/2182 | 100.0% | - |
| description | 2176/2182 | 99.7% | 0.999 |
| catalog_number | 2178/2182 | 99.8% | 0.999 |
| mfr | 2181/2182 | 100.0% | - |
| finish | 2182/2182 | 100.0% | - |
| notes | 2175/2182 | 99.7% | - |

## Manufacturer vs finish confusion

Rows: the role of a gold code. Columns: where that code landed in the prediction (`missing` = absent or a different value).

| gold \ pred | mfr | finish | other | missing |
|---|---|---|---|---|
| mfr | 1494 | 0 | 1 | 0 |
| finish | 0 | 1556 | 0 | 0 |

## Reliability (predicted field confidence vs exact accuracy)

| bucket | count | accuracy |
|---|---|---|
| [0.0, 0.2) | 0 | - |
| [0.2, 0.4) | 0 | - |
| [0.4, 0.6) | 0 | - |
| [0.6, 0.8) | 0 | - |
| [0.8, 0.9) | 124 | 100.0% |
| [0.9, 1.0] | 12968 | 99.9% |

## 10 worst errors

| # | kind | doc | set | page | line | field | gold | pred | link |
|---|---|---|---|---|---|---|---|---|---|
| 1 | wrong_mfr | roselle-public-library--087100-fl-door-hardware-ifb-revised | 6.1 | 17 | L17_13 | mfr | TRINE | ∅ | [open](http://localhost:8000/#doc=roselle-public-library--087100-fl-door-hardware-ifb-revised&set=22) |
| 2 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | description | Overhead Stop(s) | Overhead Stop(s) Active Leaf | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 3 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | description | Closer(s) | Closer(s) Top Jamb Mount | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 4 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | notes | Active Leaf | ∅ | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 5 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 02 | 20 | L20_2 | notes | Top Jamb Mount | ∅ | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=2) |
| 6 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 31 | 34 | L34_18 | description | Push to Lock Button | Push to Lock Button Shared with D147A | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=30) |
| 7 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 31 | 34 | L34_18 | description | Wiring Diagrams | Wiring Diagrams Interlock with D147A. | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=30) |
| 8 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 31 | 34 | L34_18 | notes | Shared with D147A | ∅ | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=30) |
| 9 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 32 | 35 | L35_2 | description | Push to Lock Button | Push to Lock Button Shared with D14B | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=31) |
| 10 | wrong_field | 2353-gerrard-street-shelter--hdw-spec-sch-ift-5 | 32 | 35 | L35_2 | description | Wiring Diagrams | Wiring Diagrams Interlock with D147B. | [open](http://localhost:8000/#doc=2353-gerrard-street-shelter--hdw-spec-sch-ift-5&set=31) |
