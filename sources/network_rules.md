# Network, connection and symmetry rules

Rules used to build the maps (all regions). Values in **bold** are the parameters. All items confirmed (November 2026).

---

## 1. Services
1.1 Only public / publicly subsidised operators (ALSA counts as public in Spain; BlaBlaCar and similar excluded).
1.2 Modes: **national railways** (red: Renfe, ÖBB, SBB incl. S-Bahn), **local railways** (green: Euskotren, narrow-gauge, rack railways, trams), **regional buses** (blue).
1.3 Regional buses only: a bus route must serve **≥ 2 municipalities** and have a trip of **≥ 5 km** (straight-line sum between stops). Town buses are dropped.
1.4 A route (line) is identified by its GTFS route id (shown by its short name), so different lines with the same number (e.g. two SBB "S3") stay apart.
1.5 Days: a representative weekday, Saturday and Sunday. Time bands: **peak 07–09 + 17–19**, **day 09–17**, **night 22–06** (whole hours). The map always shows the selected day and band.

## 2. Nodes
2.1 **Candidate stations**, per municipality and mode (OpenStreetMap municipality polygons): stops within a **5-min walk (~375 m)** of each other form one station.
   - Rail: every station is a candidate.
   - Bus: a stop group is a candidate if it is the bus station, lies next to a train station (**≤ 500 m**), or is served by **≥ 2 regional bus lines** (avoids every street corner of a city becoming a candidate).
   - The main station of a municipality and mode: rail "<Town> Hauptbahnhof / Bahnhof" or the stop served by most lines; bus = bus station, or the best-served stop next to the train station.
   - Each stop belongs to the nearest candidate station of its municipality and mode.
2.1a Every candidate station is judged on its own (2.5): a municipality can end up with **no node, one, or several** (two important stations of one mode; train and bus station). Names: the municipality, plus the station name when the municipality has several nodes of that mode (e.g. "Linz · Hbf", "Linz · Urfahr").
2.2 A trip visits a node when it stops within **1 km** (rail) / **1.5 km** (bus) of the station; the time of the stop closest to the station is used.
2.3 A trip that only passes through the municipality (a stop up to **8 km** from the station) serves it on the map (line drawn), but these stops are not station visits: they are not used for connections or symmetry.
2.4 Stations of different modes are merged into one map node when the walk is **≤ 2 min** (same building).
2.5 **Branching is always required.** A station is a node only if it is a **branch**: it reaches **≥ 3 directions** (neighbouring municipalities, or neighbouring stations of the own municipality). Stations within walking distance (any mode, any municipality) count only if together they reach a third direction (train A–X–B next to bus A–X'–B is not a branch).
   The only exception: a **route terminus** — a station where all trips start or end, or where **≥ 30 %** of the trips of some route that reach the station start or end there. A route terminus is always a node, also outside the region (so a route leaving the region is drawn up to its end), and is never removed by the 2-min rule.
   Nothing else justifies a node (no "line end ≥ 10 %", no "bypassed important stop" exceptions). Non-branch stations are removed and their neighbours linked directly.
2.5a **Redundant stations.** A branching station is kept only if it offers at least one change between two lines that cannot be made at any other node (lines of stations within walking distance count as its own). If every pair of its lines also meets at another node, it is removed and its neighbours are linked directly — e.g. Buttisholz (lines 60/61/62 all also stop at Ruswil: Ruswil now links straight to Ettiswil and Sursee), Werthenstein (its train and bus lines also meet at Malters / Wolhusen). Removal order: smaller municipality first (WorldPop population of the municipality), secondary stations of a town before its main one, then fewer departures; re-checked after each removal, then the branch rule is applied again.
   A route terminus is kept as a node only if the last stretch of that route is not also run by other trips that continue beyond it (Buttisholz: line 60 ends there, but 61/62 continue).
2.5b **Every route stays drawable**: after all removals, a route whose trips mostly reach fewer than 2 nodes, or that serves the region but has no node inside it, gets its end stations back as nodes.
2.6 Outside municipalities appear only as hubs with **≥ 150** departures a day, or as route termini (2.5).

## 3. Links (map lines)
3.1 A link joins consecutive node visits of the same trip and mode.
3.2 Links shorter than **2 min** are collapsed (the less important node is removed). Links shorter than **10 min** are kept only if both stations are needed for connections (a timed connection or a symmetry in some time band); otherwise the less important station (smaller municipality, fewer departures) is removed — also an end station — and its neighbours are linked directly. Two stations of the **same mode in the same municipality** less than 10 min apart are one place: the secondary one is removed whatever its connections (e.g. Donostia Urbieta / Etxaide next to the bus station). Repeated until stable; a line always keeps at least two nodes.
3.3 Implausible legs (straight-line speed above the mode maximum, detours much slower than the route's usual time) are removed.
3.4 Night view: a link is shown only if it has a service between **00:00 and 05:00**.

## 4. Headways
4.1 pyGTFSHandler formula, all services of the measured stream pooled together (never one headway per line merged afterwards):
    headway = (first gap² + Σ gaps²) / window, summed over the windows of the band, with first gap = (first − start) + (end − last).
4.2 Edge headways are given per direction: **in** = arrivals from that edge, **out** = departures to that edge.
4.3 **Frequent** = headway **under 15 min** (e.g. 14.8 min is frequent; exactly 15 min is not).
4.4 One-off or few exceptional services barely change the formula, so they need no special treatment.

## 5. Edges
5.1 An **edge** of a node = one direction out of the node: towards one neighbouring town, for one mode, at one station (own station or a station reached on foot).
5.2 **Fast / slow edges**: the services of an edge are split into a fast and a slow group only if
   - the slow group makes **≥ 2 more stops** and takes **≥ 6 min more** travel time than the fast group (to the same next node), and
   - the two groups have similar headways: the less frequent group's headway is **at most twice** the better group's, and
   - each group has **≥ 6 trips a day**.
   Otherwise all services form one edge. When split, the edge is treated as two different edges ("Town (fast)", "Town (slow)") in all computations below and in the node popup. The map does **not** draw a second line or an extra node.
5.3 Fast services that skip the next node altogether reach another neighbouring town and therefore are already a different edge (e.g. Sursee: IR to Luzern vs S-Bahn to Nottwil). Changes between such edges in the same travel direction are treated like any other pair of edges.

## 6. Walking
6.1 Walking transfer only up to **5 min** (75 m/min, straight line × 1.3), between any two stations (any mode, any municipality).
6.2 Changing mode or station adds **2 min** to the walk.

## 7. Travel options between two edges (direction A → B at a node)
7.1 **Direct option**: the same vehicle arrives from A and continues to B.
7.2 **Change option**: arrival from A, then the first departure to B on another vehicle, with
   - wait = departure − arrival − walk (walk incl. the 2-min penalty),
   - wait **≤ 6 min**, or **≤ 12 min** when arriving by bus (bus → bus, bus → train).
   Longer waits are not coordinated changes.
7.2a Pairs of edges that lead the same way (directions less than **45°** apart, e.g. IC to Basel and regional train to Gelterkinden at Olten) are not relations: changing between them means going back. They are left out everywhere.
7.3 Not a change: two trips of the **same line** (e.g. S6 arriving and S6 leaving onwards at Wolhusen, where the timetable splits the trip) — that is a direct service. Also not a change: the arriving vehicle reaches B's town anyway later, or the departing vehicle has already come from A's town (same vehicle / going back).
7.4 A change option counts only if
   - no other option (direct or change) arrives from A at the same time or later and leaves towards B at the same time or earlier (not overtaken), and
   - it gains at least **min(30 min, 25 % of the direct headway)** over the next direct service available after the same arrival (if there is any direct service).
7.5 **Hd** = headway of the direct options; **Hc** = headway of direct + counted change options (formula 4.1, departure times towards B).

## 8. Connection (one direction A → B)
8.1 If the **relation itself** is frequent — its real headway with all services (direct ones included, 10.2 line 2) is under 15 min — **no coordination needed** (a frequent feeder towards a line every 30 min is NOT frequent: the relation still runs every 30 min). Shown as "frequent"; left out of all symmetry shares.
8.2 Otherwise the direction is **connected (coordinated)** when all of
   - there are **≥ 2** counted change options in the band (it repeats),
   - **Hc ≤ Hd / 2** (with the changes the headway is at least twice as good as with direct services only; any Hc if there is no direct service),
   - **Hc ≤ 1.25 × H_worst**: most services of the worse edge connect (note Hc can never be better than H_worst, the headway of the worse of the two edges — every option uses one arrival from A and one departure to B),
   (No separate 'better than random' test: the wait limits of 7.2 — 6 min, 12 min arriving by bus — are the criterion.)
8.2a Also connected: if with **all services** (real timetable, 10.2 line 2) the **mean wait** is within the limit (≤ 6 min, ≤ 12 min arriving by bus; rounded to the minute) and there are ≥ 2 such changes (and, if there is a direct service, the headway is at least twice as good).
8.3 Otherwise: "not timed" (services exist but coordination adds nothing).
8.4 Weight of a direction, used for **every** percentage (75 % rule, both-ways / one-way shares, group size): the **frequency** of the worse of its two edges (60 / its headway = connection opportunities per hour). An hourly relation counts 1, a half-hourly one 2, one every 8 hours 0.125, so rare relations barely count.

## 9. Symmetry
9.1 Relations needing no coordination (8.1) are ignored. If they make up **≥ 75 %** of a node's relations (weighted by the worse edge's headway, 8.4), the node has no symmetry (not needed).
9.2 Every connected direction has a **change minute**: the middle between arrival and departure of its counted changes.
9.3 Connected directions are grouped by change minute (modulo 30 min, tolerance **± 5 min**). Groups closer than **10 min** are merged. Each group with **≥ 2** connected directions whose timed changes involve **≥ 3 different neighbouring stations** (fast / slow edges and stations reached on foot count once) is a candidate symmetry.
9.4 Symmetry minute(s) of a group: its change minutes around the group centre and/or centre + 30 min (each hand needs **≥ 20 %** of the changes); rounded to a multiple of 5 only when within 1 min.
9.5 Completeness, over the pairs of the group's edges in which at least one direction needs coordination (each pair weighted by the headway of its worse edge, 8.4). A direction **works** when it is connected in this symmetry **or in another symmetry of the same node** (e.g. Olten → Zug at :05, Zug → Olten at :53 at Luzern), or needs no coordination (frequent, 8.1, or served directly, 8.1a), or has no service at all (one-way relation).
   - **Complete** (solid hand): more than **50 %** of the pairs work in **both** directions.
   - **Half** (dotted hand): otherwise, if more than **50 %** of the pairs are connected (timed) in at least one direction.
   - A group whose timed connections run every **≤ 60 min** (median headway with changes) **always** makes the node symmetric (half, or complete if > 50 % works both ways), even below the 50 % one-way share.
   - Otherwise no symmetry.
   (Directions served directly or by frequent lines no longer count against completeness: before, a pair whose reverse direction ran by through train made a complete node look half.)
9.6 The **largest** symmetry (by weight) is drawn on the map symbol; the popup lists all symmetries.

## 10. Map and popups
10.1 Node popup: symmetries as clickable clock cards (S1, S2, …); selecting one shows only its connections; "show all" returns.
10.1a Node diagram (one spoke per neighbour at its real bearing): solid = works both ways in the selected symmetry, dashed = one way, grey = not in the symmetry, wide light line = frequent (< 15 min). One label on each spoke, in a pill on the line: "◀ min′ ↻headway │ ↻headway min′ ▶" — arrival (arrow towards the node) = minutes before the symmetry minute, departure (arrow away) = minutes after it; ↻ = headway of only the symmetry services of that direction. Symmetry spokes: median of the group's timed changes (only within 6 min rail / 12 min bus). Frequent and grey spokes: mean, over every symmetry minute in the band, of the gap to the last arrival before it and the next departure after it (all services), no ↻; gaps longer than 30 min are not shown. Under the name, in grey: headway of the edge, all services ("arr′/dep′" when they differ); at most 3 line names (short form) + "+n". Directions served at a walk partner (another node within 5 min walk) are drawn only in the symmetries that use them, with "🚶 X′" after the name. Labels are placed without overlaps: the spoke labels move outward until they touch no other label or spoke (grey ones that cannot be placed cleanly are left out); the names are stacked in one column per side, with a thin leader line when moved from the spoke tip.
10.2 **Edge connections** table: Edge A | ← | → | Edge B, ordered rail–rail, rail–local rail, local–local, rail–bus, local–bus, bus–bus; within each, connected first, then by wait. Each edge shows its in / out headways; fast / slow edges are labelled.
     Each direction shows two lines: (1) with timing: mean wait (+ walk) of the timed changes and the headway of timed changes + direct services — or "not timed" / "frequent" / "direct"; (2) all services, real timetable: every arrival takes the first departure towards the other edge, the same vehicle continuing counts with wait 0; (3) if there are direct services: their headway; when several arrivals catch the same departure only the latest counts; mean wait (+ walk) and headway of these trips.
10.3 **Route connections** table: the same layout for the lines involved in the counted changes (route · town), with number of changes, mean wait, walk and symmetry tag.
10.4 Edge (link) popup: travel times, services, lines, longest wait, and one box per direction with its headway and departure minutes.
10.5 Legend: number of symmetry nodes in the selected day / band; ⓘ panel with these rules in short and an animation of a pulse at an invented station; "Connected only" keeps only the links that belong to a symmetry group (at either end, selected day / band) and hides nodes left without links. In the video, "Connected only" shows only vehicles on those links whose trip takes part in a timed change of a symmetry group.
10.6 Video: vehicles appear ≤ 0.5 s before moving and disappear ≤ 0.5 s after stopping; stopped ≤ 10 min shown, never longer than the best line's headway at the station; "Hide frequent lines" (≤ 14 min, per link and band) and "Connected only" checkboxes.
