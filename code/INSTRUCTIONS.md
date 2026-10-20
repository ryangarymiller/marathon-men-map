# Project: "Marathon Men" knowledge map

You are the **lead (orchestrator)** of a multi-agent research project. The user explicitly asks you to run it
as a multi-agent workflow: one lead agent in control, plus sub-agents that you create, re-task and shut
down as the work requires. Use whatever orchestration your environment offers (workflows, background
agents, message passing). Work at maximum effort and don't stop at a first draft.

## 1. Goal

TrueAnon's three-part series "Marathon Men" (episodes 220, 221, 223, April 2022, hosts **Brace** and **Liz**,
guests **Ben Howard** and **Howie**) retells the 2013 Boston Marathon bombing and connects it to many people,
events and institutions that the usual account leaves out: FBI informants, the 2011 Waltham triple murder,
Ibragim Todashev's death, Uncle Ruslan Tsarni and the CIA-adjacent world around him, Tamerlan's 2012 trip to
Dagestan, the friends, the trial, and more.

Build an **interactive, easy-to-read map** of all of it: every player, organization, place and event, how
they connect, when things happened, and **which claims are established and which are the podcast's**.
The reader is the user, on a phone as often as a desktop. They want the "crazy new lore" from the episodes
front and center, laid out so it can be absorbed in minutes, with the ability to drill into any node and
see exactly where each claim comes from.

## 2. Inputs (on this PC; you run in WSL)

- Transcripts, proofread, with speaker names (`GUEST` = Ben or Howie, unidentified):
  - `/mnt/c/Users/mille/transcripts/scripts/TrueAnon 220 Marathon Men (Part 1).txt`
  - `/mnt/c/Users/mille/transcripts/scripts/TrueAnon 221 Marathon Men (Part 2).txt`
  - `/mnt/c/Users/mille/transcripts/scripts/TrueAnon 223 Marathon Men (Part 3).txt`
  - `/mnt/c/Users/mille/transcripts/scripts/TrueAnon Marathon Men - complete series.txt` (all three)
  Each turn is `SPEAKER  [m:ss]` then the text. The time is when that turn starts in the episode.
- Machine-readable versions with the same turns and start times (seconds):
  `/home/rmiller/podscribe/work/ep220/edited.json`, `ep221/edited.json`, `ep223/edited.json`.
- Spelling authority for names: `/home/rmiller/podscribe/work/STYLE_SHEET.md`.
- Transcript caveats: these are speech-recognition transcripts that were carefully proofread, but some
  phrases remain uncertain (listed in `TrueAnon Marathon Men - open questions.txt`; episode 223 has not been
  checked by ear yet). The hosts joke constantly; separate bits and sarcasm from actual claims.
- Spotify episode IDs, for "listen at this moment" links (`https://open.spotify.com/episode/<id>?t=<seconds>`):
  220 `5H4vhwj5Et8xOqjibGjyzI`, 221 `4K6BXGfHqmkm90pMas3tT5`, 223 `6A2gd9ROULkcZebWQOaLKf`.
  The Spotify audio matches the transcript timing to within about a second.

## 3. Ground rules (apply to every agent)

**Every claim is tagged.** A claim is one checkable statement ("Tamerlan was placed on the TIDE watch list
in 2011"). Each one gets a status:

| Status | Meaning |
|---|---|
| `ESTABLISHED` | Supported by court records, official reports, or multiple reputable outlets. |
| `REPORTED` | Reported by at least one credible outlet or book, not contradicted, but not confirmed elsewhere. |
| `DISPUTED` | Credible sources conflict, or officials deny it. Show both sides. |
| `PODCAST-ONLY` | Said or argued in the episodes; no outside source found either way. |
| `SPECULATION` | The hosts or guests present it as a theory or inference ("I think this was a hit squad"). |
| `CONTRADICTED` | Outside evidence goes against it. Keep it on the map, clearly marked. |

**Every claim cites where it came from:** episode + timestamp (and speaker) for podcast claims, URL or
document + page/section for outside sources. No citation, no claim.

**Every source is rated:** `A` court/official record · `B` major outlet or published book ·
`C` regional/independent journalism · `D` blogs, forums, social media, fringe sites. The user wants D-tier
sources included, but a claim cannot reach `ESTABLISHED` or `REPORTED` on D-tier sources alone.

**Never invent.** If a date, place or link can't be found, leave it empty and say so. Don't "fix" what the
speakers said; record their version, then record what sources say. Speaker factual slips (wrong weekday,
wrong age) are worth noting as such, not as new lore.

**Real people.** Victims are named respectfully and never as "lore". For private individuals who were never
charged (friends, roommates, acquaintances), use only what published sources or the episodes say, never add
addresses or contact details, and don't state guilt or wrongdoing beyond what the sources support. Accusations
belong in claims with their status, not in an entity's description.

**Use the canonical spellings** in the style sheet (Dzhokhar, Tsarnaev, Todashev, Michele McPhee, Wai Kru…);
record common variants as aliases so searches work.

## 4. Shared data model (the blackboard)

Keep all knowledge in `/home/rmiller/podscribe/map/kb/` as JSON. To avoid agents overwriting each other,
**each agent writes only to its own inbox file** (`kb/inbox/<agent-name>.jsonl`, one object per line). Only the
Curator merges inboxes into the canonical files:

- `entities.json`: `{id, type: person|org|place|event|document|media|object, name, aliases[], summary,
  dates{born,died,active}, location_ids[], tags[], episodes[220|221|223]}`
- `relations.json`: `{id, from, to, kind (e.g. family, met, employed_by, informant_for, investigated,
  owned, attended, killed, funded, member_of), start, end, claim_ids[]}`
- `events.json`: `{id, title, date (ISO; ranges allowed; precision: day|month|year|approx), place_id,
  participants[], claim_ids[]}`
- `claims.json`: `{id, text, status, said_by (speaker or source), podcast_refs[{ep, t_seconds, speaker,
  quote}], evidence_for[{source_id, note}], evidence_against[{source_id, note}], bombshell_score 0-5, why_it_matters}`
- `sources.json`: `{id, title, publisher, author, date, url, tier A-D, notes}`
- `places.json` may be folded into entities, but places need `lat, lon` for the map.

IDs are stable slugs (`person-tamerlan-tsarnaev`, `event-waltham-murders-2011`). The Curator resolves
duplicates and keeps an `aliases` map so agents can reuse IDs. A `kb/queue.json` holds open work items
(leads to research, conflicts to resolve, gaps to fill) that the lead assigns.

## 5. Team (create, re-task and retire these dynamically)

- **Lead (you).** Plans phases, keeps the work queue, spawns and retires agents based on the backlog, settles
  conflicts the Curator can't, decides when each phase is done. Keep 4–10 agents active at a time; spin up
  more for a big backlog, retire idle ones. Message agents directly when another agent's finding affects them.
- **Transcript miners** (start with ~6: two per episode, each on half). Extract every person, org, place, date,
  event and claim mentioned, with timestamps and quotes, into their inbox. Separate jokes from claims.
- **Curator** (one, long-lived). Merges inboxes, de-duplicates, assigns IDs, maintains aliases, flags conflicts
  into the queue. The single writer of the canonical files.
- **Official-record researcher.** Builds the mainstream baseline first: Wikipedia's "Boston Marathon bombing"
  article and related articles (the Tsarnaev brothers, MIT shooting, Watertown, the trial, *United States v.
  Tsarnaev*), with their references. This is the "official narrative" the map is compared against.
- **Topic researchers** (spawned per cluster from the queue, retired when done). Likely clusters:
  1. FBI informants and entrapment context the hosts raise (Emad Salem/1993 WTC, Whitey Bulger, the Whitmer
     plot, Anwar al-Awlaki and *Inspire*), and the FBI's prior contact with Tamerlan.
  2. Russia's 2011 FSB warning, the TIDE/TECS listings, the 2014 Inspector General report, the
     Graham–Napolitano hearing.
  3. Tamerlan's 2012 Dagestan trip: William Plotnikov, Mahmoud Mansur Nidal, Magomed Kartashov and the
     Union of the Just, the Fund for the Caucasus and Jamestown Foundation conference.
  4. Uncle Ruslan Tsarni, the Congress of Chechen International Organizations, Graham Fuller, USAID-contracted
     firms, Maret Tsarnaev, Nicholas and Ruth Daniloff, Khassan Baiev, Joanna Herlihy, 410 Norfolk Street,
     Alexander Lipson.
  5. The September 11, 2011 Waltham triple murder (Brendan Mess, Erik Weissman, Raphael Teken), Safwan
     Madarati, the drug and informant angle, Ibragim Todashev's 2013 killing in Orlando (FBI agent Aaron
     McFarlane), Ashurmamad Miraliev.
  6. The bombing day, the JFK Library fire, the Saudi student (Abdulrahman Alharbi), Sean Collier's killing at
     MIT, the Dun Meng carjacking, Watertown, the boat (David Henneberry), the "Boston Strong" response.
  7. Daniel Morley and the Cambridge bomb-materials case; the gun's path (Maine, Hamadi Hassan's crew,
     Binyam Sagai, Stephen Silva); Wai Kru.
  8. Dzhokhar's friends (Dias Kadyrbayev, Azamat Tazhayakov, Robel Phillipos, Khairullozhon Matanov, Viskhan
     Vakhabov), Katherine Russell, the hospital interrogation and Miranda issue.
  9. The trial and appeals: venue (the Boston survey), Judy Clarke, Judge O'Toole, the First Circuit
     (2020, death sentence vacated; Judge Torruella's earlier dissent on venue), the Supreme Court (2022,
     reinstated), Brady/withheld-evidence issues.
  10. Media and books: Masha Gessen's *The Brothers*, Michele McPhee's *Maximum Harm*, the Rolling Stone cover,
      *Patriots Day* (2016).
  These are starting points from a reading of the transcripts: **leads to verify, not facts.** Researchers add
  new clusters to the queue as they find them.
- **Verifier (adversarial).** Re-checks every claim marked `ESTABLISHED` or `CONTRADICTED`, plus every claim
  with `bombshell_score` ≥ 4, against its cited sources, and downgrades anything that isn't supported.
  Different agent from whoever found it.
- **Timeline builder.** Turns events into a clean chronology from roughly 1986 (Daniloff in the USSR) and 1993
  (WTC bombing) through 2002 (family arrives), 2011–2013 (the core) and 2022 (Supreme Court), noting date
  precision and conflicts.
- **Map/geo builder.** Geocodes places: Boston/Cambridge/Watertown/Waltham/Allston/Revere/New Bedford/UMass
  Dartmouth, Dagestan/Makhachkala, Chechnya, Kyrgyzstan/Tokmok, Kazakhstan, Orlando, Washington, D.C.
- **Front-end builder.** Builds the page (section 7) from the canonical JSON.
- **QA reader.** Reads the finished page as a newcomer would, reports anything confusing, unsourced or
  wrongly tagged, and spot-checks 20 random claims end to end (transcript timestamp → source).

Agents communicate through the queue and inbox files, plus direct messages for anything urgent ("Waltham
date conflicts with the IG report"). Every agent reads `kb/` (canonical files plus the queue) before starting
a task, so nobody redoes finished work.

## 6. Phases (the lead decides when each is done)

1. **Baseline and extraction, in parallel.** The official-record researcher builds the mainstream account
   while the miners extract everything from the transcripts. The Curator merges continuously.
2. **Clustering.** The lead groups entities and claims into topic clusters, fills the queue, and spawns topic
   researchers.
3. **Research and tagging.** Researchers attach outside evidence to claims, add the entities and relations
   they find, and set statuses. They send new leads to the queue and retire when their cluster is done.
4. **Verification.** The Verifier works through the high-impact claims. The lead resolves disputes.
5. **Build.** Timeline, geocoding and the page.
6. **QA and polish.** Fix what QA finds, then re-run QA. Done when QA passes and every node, claim and
   timeline entry on the page has a citation.

Keep a running `map/LOG.md` (decisions, conflicts, what's still open) so the work can resume if interrupted.

## 7. The deliverable: one interactive web page

A single self-contained HTML page (data embedded as JSON), saved to
`/mnt/c/Users/mille/transcripts/scripts/marathon-men-map.html` **and** published as a private Artifact, so
the user can open it on their phone. Mobile-first: it must work well on a phone screen.

Views (tabs):
1. **Start here.** A 2-minute read. "The official story" in about 10 bullets, then **"What the episodes add"**:
   the top 15–25 bombshells ranked by `bombshell_score`, each one line, with its status badge and a tap-through
   to details.
2. **Web.** A network graph of people, orgs, places and events (colored by type, edge style by relation kind).
   Filter by episode, cluster, claim status, and "official story only" vs "everything". Tapping a node opens a
   side panel: summary, its relations, every claim about it with status and sources, and "listen" links that
   open Spotify at the timestamp.
3. **Timeline.** Swimlanes per cluster (or per main person), zoomable, date precision shown.
4. **Map.** Places with pins; tapping shows what happened there and when.
5. **Claims.** A searchable, filterable table of every claim: status, who said it, episode link, sources.
6. **Sources.** Every source with its tier.

Make the status legend visible on every view, and use the same status colors everywhere. Speculation must look
different from established fact at a glance. Include a short "How to read this" note and a "Last built" date.
Libraries from cdnjs only (for example vis-network or Cytoscape for the graph, Leaflet for the map), pinned to
exact versions.

Also save the knowledge base as `marathon-men-kb.json` next to the page, so it can be reused.

## 8. Quality bar

- Every node, edge, timeline item and claim traces to a transcript timestamp or a source. Spot checks must pass.
- No claim reads as `ESTABLISHED` because a host said it confidently.
- The "Start here" view gives a newcomer the official story and the episodes' biggest additions in under five
  minutes.
- Names are spelled per the style sheet; aliases make the search forgiving.
- When you finish, report to the user: what's on the map (counts by type and status), the top bombshells and
  how they checked out, the biggest open questions, and anything you couldn't verify.
