# Marketing Content Plan

Grounded in `docs/DatFe_Pricing_Strategy.docx`'s positioning, not
invented separately - the target buyer, competitive angle, and GTM
motion described there are the inputs to everything below. This is a
living document; revise it once real content is published and its
performance is visible in the funnel data DatFe already tracks (see
"Measuring this" at the end - that part is not aspirational, it's
already built).

## Who this is for

One buyer, described precisely in the pricing doc: a head of data,
ops, or engineering at a 20-300 person company, 3-20 operational data
sources, no dedicated governance function. They're pulled in by one of
three triggers - a compliance requirement a spreadsheet can't satisfy
credibly, "who owns this table" friction as the team outgrows tribal
knowledge, or onboarding a new hire who needs context that lives in
one person's head. They've likely already looked at Atlan or Select
Star, gotten quoted a number sized for a platform team, and are
currently doing nothing (or maintaining a spreadsheet). Every piece of
content should be useful to that specific person, not a generic "data
governance is important" pitch.

## Content pillars

Four recurring themes, each tied to a real trigger or competitive gap
rather than a generic topic list:

1. **"Who owns this?" friction** - the day-to-day pain of tribal
   knowledge. Concrete, story-driven ("a new analyst spent two weeks
   figuring out which `customer` table was real"), not abstract.
2. **DPDP/GDPR-style compliance for small teams** - practical, not
   legal-advice-flavored (stays consistent with the brand voice rule
   against oversell on compliance topics - see
   `docs/DatFe_Brand_Guidelines.docx`). "Here's what a PII inventory
   actually requires" over "achieve compliance instantly."
3. **Transparent pricing as the differentiator** - direct comparison
   content. Collibra/Informatica's opacity and Atlan's per-seat cliff
   past one user are real, citable gaps (see the pricing doc's
   competitive table) - "how much does \[X\] actually cost" content
   performs well precisely because competitors won't publish numbers.
4. **Product-led proof** - short, specific posts built from real
   product capability (lineage-adjusted quality scores, the NL Ask
   assistant, column-level lineage) rather than feature-announcement
   posts. Show the thing working on a realistic example.

## Formats and channels

Prioritized for a solo operator - depth over volume, and every format
should be reusable across channels rather than written once and
forgotten:

- **Long-form blog / SEO posts** on the marketing site (new `/blog/`
  section - doesn't exist yet). Primary home for pillars 1-3. Aim for
  content that ranks for buyer-intent searches ("data catalog pricing
  comparison," "DPDP data inventory template," "who owns this data
  table") rather than broad awareness terms that only well-funded
  competitors can win.
- **Comparison pages** - "DatFe vs Atlan," "DatFe vs Collibra" as
  standalone pages, not just blog posts. These convert unusually well
  for a self-serve product because the visitor has already decided
  they need a catalog and is actively comparing - exactly the
  "evaluated Atlan, got quoted a number" buyer the pricing doc
  describes.
- **LinkedIn** - where this buyer actually spends time (data/ops
  leads, not consumer social). Repurpose blog posts as native
  LinkedIn posts rather than just links - link posts get suppressed
  by the platform's own algorithm.
- **Changelog / "what shipped"** - short, on the marketing site or as
  a LinkedIn post per meaningful release. Costs almost nothing since
  it's a summary of work already done, and signals an actively
  developed product to anyone evaluating.
- **Not yet**: paid ads, video, a podcast, or guest posting - all
  real channels eventually, but each has setup cost that competes
  with actually writing the first 10-15 pieces of pillar content.
  Revisit once organic content has a baseline to compare paid against.

## Cadence

Realistic for one person, not aspirational: **one substantial piece
every 1-2 weeks**, alternating pillars so the blog doesn't read as
single-note. A comparison page counts as a substantial piece. A
changelog post does not count toward this cadence - it's free
overhead, publish one whenever something real ships.

Better to publish 20 genuinely useful pieces over the next year than
commit to weekly and quietly stop in month two - the second pattern
is worse for a domain's search credibility than a slower, honest
cadence.

## Measuring this

Not a gap to build - already exists. The marketing site's visitor
tracking (`anon_id`, tied through to signup via
`marketing_service.link_anon_id_to_signup`) and the Platform Admin
dashboard's funnel stats mean any new content page's actual signup
contribution is measurable from day one, not just pageviews. Practical
habit to adopt: tag outbound links from each new post/page with a
distinct `?anon_id`-compatible source marker so the funnel breakdown
can eventually answer "which pillar actually produces signups," not
just "how much traffic did we get."

## Where prospect pipeline gets logged

Once a piece of content produces a real lead (a demo request, an
inbound email), log it in `docs/DatFe_Business_Tracker.xlsx`'s Leads
& Demo Requests sheet - the Source column exists specifically to
capture which channel/content it came from, so content ROI can be
checked against the tracker's pipeline data, not just funnel
pageviews. See that workbook's own Instructions sheet for the full
convention - the point made in "When to graduate off this workbook"
also applies here: this content plan itself should get revisited (not
necessarily replaced) once there's real performance data to react to,
rather than staying a one-time document.
