# Clock-face scheduling / Taktfahrplan / ITF — literature notes

All PDFs listed under "Local copies" are in `literature/papers/`. Quotes below were taken from the PDF text (page = PDF page).
Statements without a local source are marked *(web, not verified in full text)*.

## Local copies

| File | Reference | Type |
|---|---|---|
| `Fischer_2024_OeBB_Zielnetz_TUWien.pdf` | Fischer, U. (ÖBB-Infrastruktur AG): *Das Zielnetz – Basis für den langfristigen Bahnausbau in Österreich*. Ringvorlesung Öffentlicher Verkehr, TU Wien, 31.01.2024 | Slides (Austria presentation) |
| `BMK_Zielnetz2040_Fachentwurf.pdf` | BMK / ÖBB-Infrastruktur / SCHIG: *Zielnetz 2040 – Das Bahnnetz der Zukunft, Fachentwurf*. Wien, 2024, 144 p. | Official plan |
| `Hesse_etal_2000_ITF.pdf` | Hesse, W., Guckert, M. (Univ. Marburg), Schneider, J., Schulz, A. (BEG): *Werkzeuggestützte Entwicklung eines Integralen Taktfahrplans mit OptiPlan* (c. 2000) | Paper (Bavarian ITF case) |
| `Teichmann_2007_ITF_Planung.pdf` | Teichmann, C. (TU Darmstadt): *Der Integrale Taktfahrplan (ITF), Modell mit Zukunft?* Eisenbahntechnisches Kolloquium 2007 | Talk paper |
| `Kraft_Thalmann_2022_Anschlussoptimierung.pdf` | Kraft, C., Thalmann, D.: *Entwicklung einer Methode und Kalkulationstabelle zur Anschlussoptimierung des ÖSPV an Schweizer Bahnknoten*. BSc thesis, HSLU, 2022 (with Stadtbus Winterthur) | Thesis (bus–rail connections) |
| `Riedmueller_Lindner_2025_Column_Generation_Periodic_Timetabling.pdf` | Riedmüller, S., Lindner, N.: *Column Generation for Periodic Timetabling*. arXiv:2510.12466, 2025 | PESP optimisation |
| `Paetzold_2019_Robust_Periodic_Timetables_Delay_Mgmt.pdf` | Pätzold, J.: *Finding Robust Periodic Timetables by Integrating Delay Management*. arXiv:1907.04554, 2019 | PESP + robustness |
| `Fuchs_etal_2025_Integrated_Periodic_Railway_Timetabling_SMT.pdf` | Fuchs, F., Martin-Iradi, B., Corman, F.: *Solving Integrated Periodic Railway Timetabling with SMT*. arXiv:2507.11489, 2025 | PESP + vehicle circulation |
| `Schiewe_Schoebel_2021_Integrated_Optimization_Public_Transport.pdf` | Schiewe, P., Schöbel, A.: *Integrated Optimization of Sequential Processes: General Analysis and Application to Public Transport*. arXiv:2109.10158, 2021 | Integrated planning |

## Core concepts (grounded)

**Taktfahrplan vs. ITF.** "Ein Taktfahrplan bedeutet, dass die Kurse einer Linie in einem fixen Taktabstand fahren. Ein Integraler
Taktfahrplan (ITF) unterscheidet sich … insofern, dass der ITF nicht für jede Linie einzeln geplant wird. Die einzelnen Taktfahrpläne
der Bahn- und ÖSPV-Linien werden in den Knoten aufeinander abgestimmt." — Kraft & Thalmann 2022, p. 10.
For urban bus networks "wird der Bahnfahrplan zuerst erstellt und danach die ÖSPV-Anschlüsse möglichst optimal an die
Bahnabfahrten und -ankünfte angepasst" (ibid.). → our tool treats rail as the backbone and checks whether buses meet it.

**Austrian ITF goal.** The ITF should give "optimale Anschlüsse in alle Richtungen – jeweils möglichst zur wiederkehrenden und dadurch
leicht merkbaren Abfahrtsminute … Mit dem ITF sollen die Umsteigezeiten im gesamten Verkehrsnetz reduziert werden … Das Grundgerüst
des österreichischen ITF bildet der hochrangige Eisenbahn-Fernverkehr, auf welchen der Regional- und Nahverkehr in den Knotenpunkten
abgestimmt wird." — Zielnetz 2040, p. 45.

**Symmetry minute.** "Um in Europa eine grenzüberschreitende bzw. netzübergreifende Abstimmung von Fahrplänen zu ermöglichen, wird die
sogenannte ‚Symmetrieminute 00' als wesentliche Planungsprämisse herangezogen." — Zielnetz 2040, p. 29 (fn. 9).

**Node–edge model (Knoten-Kanten-Modell).** "Das Knoten-Kanten-Modell für den Integralen Taktfahrplan (ITF) bildet eine wesentliche
Grundlage für die Weiterentwicklung der Angebotskonzepte im Personenverkehr. Besonderes Augenmerk liegt dabei auf der Optimierung der
Taktknoten" — Zielnetz 2040, p. 29. Edge times move node times: "Die Verkürzung der Kantenfahrzeiten zwischen Linz und Salzburg bewirkt
eine Drehung des Taktknotens Salzburg auf die Minute 15 bzw. 45" — p. 46. (So a node can be a valid symmetry node at :15/:45, not only :00/:30.)

**Edge-time rule.** Ideal conditions in the Bavarian ITF study: "Die wichtigsten Umsteigebahnhöfe sind als Vollknoten ausgelegt, die
Hauptknotenzeiten sind dort 00 oder 30. Die Kantenzeiten zwischen den wichtigen Umsteigebahnhöfen betragen n · T/2 − D Minuten
(mit n = 1,2,…; T = 60 oder 120 und D ≈ 3–10 Minuten), also z. B. 27, 56 oder 85 Minuten." — Hesse et al., p. 6.
Hourly service is the norm there; half-hourly on busy lines; two-hourly is the exception (ibid.).

**Headway levels by segment (Austria).** Table 1 of Zielnetz 2040 (p. 27): high-level long-distance links between Taktknoten every
60 min nationally (120 min internationally). p. 48: at least 1 Systemtrasse per hour and direction, 2 per hour on strong corridors,
"um in den Taktknoten ein Angebot im Halbstundentakt für Anschlussverbindungen zu ermöglichen".

**Infrastructure cost of nodes.** During the ITF "Systemzeit" many platform tracks are occupied at once, while the infrastructure is
lightly used outside it — Teichmann 2007, p. 2.

**Austrian presentation (Fischer 2024).** Zielnetz 2040 Fachentwurf: 67 projects in 25 modules, five directions, among them
"Weiterentwicklung des Taktfahrplans mit Verkürzung der Fahrzeiten", "Mehr öffentlicher Nahverkehr in den Ballungsräumen",
"Bessere Anbindung des ländlichen Raums mit Regionalbahnen"; c. €26 bn (p. 16). Travel-time targets via Taktfahrplan + better
transfers: Wien–Innsbruck −30 min, Graz–Linz −30 min, Villach–Salzburg −25 min (p. 9).

**Connection quality / waiting time.** Kraft & Thalmann define the optimal connection as one with (almost) no waiting time
(p. 23) and minimise the passenger-weighted sum of waiting times, using walking time (Wegzeit) to compute the effective
wait (pp. 25–30). → our "wait = departure − arrival − walk (+2 min when the mode or station changes)".

## Optimisation (PESP)
- The Periodic Event Scheduling Problem (Serafini & Ukovich 1989) is the standard model; "Solving instances of the benchmark library
  PESPlib to optimality continues to pose a challenge" — Riedmüller & Lindner 2025, abstract.
- Robustness / delays: Pätzold 2019 extends PESP with periodic delay management.
- Integration with vehicle circulation: Fuchs et al. 2025 (VCR-PESP, SMT); with line planning / vehicle scheduling: Schiewe & Schöbel 2021.
- *(web, not verified in full text)*: Liebchen & Peeters, cycle-based formulations; Liebchen & Möhring 2004; Peeters 2003 thesis
  (Erasmus, "Cyclic Railway Timetable Optimization"); FU Berlin disc. paper 2020/20; ZIB report ZR-21-06; Pulse timetable for rural
  networks, *Transport Policy* 52 (2016) 175–185 (doi:10.1016/j.tranpol.2016.07.012). Downloads failed (HTML landing pages / paywall).

## How the tool's rules relate to the literature
| Tool rule | Basis |
|---|---|
| Nodes = stations where lines branch, line ends, or important stops bypassed by faster services | Knoten-Kanten-Modell (Zielnetz 2040 p. 29, 46); Hesse et al. Vollknoten |
| Symmetry hands at the minute where arrivals precede and departures follow (60/30/15 patterns, not only :00) | Symmetrieminute 00 (p. 29); rotated node at :15/:45 (p. 46) |
| Wait = dep − arr − walk (+2 min change penalty) | Effective wait with Wegzeit, Kraft & Thalmann pp. 25–30 |
| Connection only if wait < ¼ of the better line's headway, repeats < 4 × that headway, regular (±5 min), better line ≥ 15 min | **Project choice** (user rule): coordination is only meaningful when random waiting would be long; not taken from a source |
| Symmetry node if > 50 % of its ≥ 15-min directions are connected > 50 % of the time | **Project choice** (user rule) |
| Rail first, buses fitted to it (bus arrivals may come up to 12 min early) | Kraft & Thalmann p. 10; Zielnetz 2040 p. 45 |

## To read next
Peeters 2003 thesis; FGSV ITF Merkblatt; SBB Fahrplanfeld studies; Basque/Spanish ITF cases (Euskotren, Cercanías) — none found yet.
