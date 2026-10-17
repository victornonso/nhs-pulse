# Source contracts

Inspected against primary publications on 17 October 2026. A discovery page is not evidence of the numerical contents of its linked file; both are retained separately.

| Family | Official contract | Observation grain | Current reference |
|---|---|---|---|
| A&E | NHS England monthly provider CSV and companion workbook | Provider or separate published national row × reporting month × attendance type | September 2026; published 8 October 2026 |
| KH03 | NHS England overnight/day-only workbooks | Provider, region or national × quarter × sector/specialty | April–June 2026; published 20 August 2026 |
| Diagnostics | DM01 full provider/commissioner CSV matrix in ZIP, companion provider workbook | Provider × commissioner × test × month, projected separately for analysis | August 2026; published 8 October 2026 |
| Identity | NHS ODS ORD API and NHS A&E system mapping workbook | ODS identity; dated provider/ICB relationship | April 2026 mapping, not back-applied to earlier months |
| Boundaries | ONS ArcGIS official boundary services | Valid-time MultiPolygon, EPSG:4326 | 36 April 2026 ICBs; seven January 2024 NHS regions |
| UEC | Optional seasonal collection | Not enabled | No inferred daily data |

## A&E

The raw CSV attendance columns are unbooked components. The headline workbook includes separately published booked appointments. The parser retains both components and serves an explicit booked-inclusive/exclusive basis. September 2026 headline attendances reconcile to **2,444,743**, including **74,952** booked attendances; four-hour performance is **74.36%** on that same denominator. The published national row is never combined with provider rows. Source variants `TOTAL` and `Total` identify the national row.

The 4–12-hour and 12+-hour waits are disjoint **decision-to-admit** bands. Neither describes time since arrival. Emergency admissions through A&E and other routes are combined only in the all-types measure. Organisational changes can affect provider comparability.

## KH03

The workbook publishes average daily available/occupied beds over a quarter. Bed-days are those averages multiplied by the actual 90–92 calendar days in that quarter. April–June 2026 has 91 days. Specialty occupied-bed observations without an available-bed denominator do not produce an occupancy percentage. Estimated returns are flagged. An official occupied-above-available anomaly is retained with a warning rather than silently capped.

## DM01

The matrix contains fifteen named tests plus `TOTAL`; subtotal test rows are excluded before aggregation. Provider and commissioner projections are separate, non-additive views. The August 2026 raw matrix sums to **1,833,070** waiting-list entries, including **5,851** under commissioner code `NONC`. Excluding NONC reconciles to the companion provider workbook's **1,827,219** NHS-commissioned total. The immutable matrix and unadjusted core projections are retained; an explicit exclusion dimension defines the analytical scope. NHS England commissioning (`X24`) is retained.

Null/suppressed cells remain null. Paired numerator/denominator coverage is required for rates. No correlation is interpreted as causation.

## Dates and scheduling

Observation period, actual publication statement, last discovery check, last successful ingestion and next announced release are distinct fields. Publication statements are read from companion workbooks where available; expected calendar dates never substitute for actual publication evidence. Date-only publication statements have date precision. UI timestamps use Europe/London; storage uses timezone-aware UTC.

The official 2026–27 calendar includes an A&E/diagnostics release on **16 April 2026**, so a fixed second-Thursday rule is unsuitable. The hourly scheduler checks due policies: hourly in the six hours following an announced publication, daily otherwise, and weekly historical revision checks. Monthly and quarterly observations are not interpolated into daily facts.

## Primary sources

- [A&E publication collection](https://www.england.nhs.uk/statistics/statistical-work-areas/ae-waiting-times-and-activity/)
- [KH03 overnight collection](https://www.england.nhs.uk/statistics/statistical-work-areas/bed-availability-and-occupancy/bed-data-overnight/)
- [Monthly diagnostics collection](https://www.england.nhs.uk/statistics/statistical-work-areas/diagnostics-waiting-times-and-activity/monthly-diagnostics-waiting-times-and-activity/)
- [Official statistics calendar](https://www.england.nhs.uk/statistics/12-months-statistics-calendar/)
- [ODS ORD API](https://digital.nhs.uk/developer/api-catalogue/organisation-data-service-ord)
- [ONS April 2026 ICB boundaries](https://www.data.gov.uk/dataset/3735c4be-8ae8-43a3-8a7c-40fec660e6e5/integrated-care-boards-april-2026-boundaries-en-bsc)
