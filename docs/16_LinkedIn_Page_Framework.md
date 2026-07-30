# LinkedIn Page Framework

LinkedIn is the primary channel called out in
`docs/15_Marketing_Content_Plan.md` - it's where the actual buyer (a
head of data/ops/engineering at a 20-300 person company) spends
working time, unlike consumer social. This doc is the setup framework
plus ready-to-use starting content, grounded in the same positioning
as the pricing and content-plan docs - nothing here is generic
"SaaS company on LinkedIn" advice.

## 1. Creating the Page

You'll need to be logged into a personal LinkedIn account to create a
Company Page (linkedin.com/company/setup/new) - that's a step only you
can do. Exact fields to fill in:

- **Page name**: `DatFe`
- **LinkedIn public URL**: `linkedin.com/company/datafe` (check
  availability first; if taken, `datafe-io` or `datafehq` as fallback
  - avoid anything with "ichnos" in it, even as a fallback, to keep a
  clean paper trail for the rebrand)
- **Website**: `https://datafetech.com`
- **Industry**: Software Development (secondary option if offered:
  Data Infrastructure and Analytics)
- **Company size**: 1-10 employees (accurate - don't inflate this;
  small-team authenticity is actually on-brand given the "built for
  companies without a dedicated platform team" positioning)
- **Company type**: Privately Held
- **Logo**: export `DatFeMark` at 300x300px from
  `frontend/src/components/DatFeLogo.tsx` (the dark squircle + copper
  hexagon mark, not the full wordmark lockup - LinkedIn's logo slot is
  square and small, the wordmark won't read at that size)
- **Cover image**: 1128x191px - a simple `--paper` (#FBF8F2) or
  `--ink` (#14121F) background with the tagline text in Unbounded,
  per `docs/DatFe_Brand_Guidelines.docx`. Avoid a busy product
  screenshot here; the cover image is prime real estate for the one
  sentence that matters most.

### Tagline (LinkedIn limits this to 120 characters)

> Metadata intelligence for teams without a data platform team.

### About section

Longer field, no strict limit but LinkedIn truncates to ~2 lines
before "see more" - front-load the hook:

> Your data has a story. DatFe helps you actually read it.
>
> DatFe is a metadata intelligence and governance platform for small
> and mid-size companies - built and priced for teams with real
> governance needs (PII exposure, scattered ownership, no single
> source of truth) but no dedicated data platform team or six-figure
> budget.
>
> Connect your sources, get automatic lineage and data quality
> scoring, and let your team stop asking "who owns this?" in Slack.
>
> Free to start - no credit card, no sales call.
>
> datafetech.com

## 2. Content pillars, mapped to LinkedIn formats

The four pillars from the content plan, translated into what actually
performs as a native LinkedIn post rather than a link-out:

| Pillar | LinkedIn format | Why this format |
|---|---|---|
| "Who owns this?" friction | Short text post (150-300 words), first-person or story-framed | LinkedIn's algorithm favors native text it can keep users reading on-platform - this pillar is inherently anecdotal, which suits it |
| DPDP/GDPR compliance for small teams | Document/carousel post (5-8 slides) | Practical, checklist-style content works better as a swipeable carousel than a wall of text - and carousels get saved/shared more, which is the highest-value engagement type for this pillar's intent-heavy audience |
| Transparent pricing differentiator | Text post with a simple comparison table as an image | Screenshot the pricing table from the marketing site or `docs/DatFe_Pricing_Strategy.docx` directly - real numbers, not a claim, is the whole point |
| Product-led proof | Short video or screen-recording (30-60 sec) if feasible, otherwise a single annotated screenshot | Showing the Ask assistant or lineage view actually working beats describing it |

Changelog posts (from the content plan) are the simplest recurring
format - one or two sentences plus a screenshot, whenever something
real ships. These don't need to fit a pillar; they exist to signal an
actively developed product.

## 3. Cadence

Matches the content plan's overall cadence rather than inventing a
separate LinkedIn-specific schedule: **2-3 posts per week**, made up
of:

- 1 pillar post (repurposed from that period's blog piece, once the
  blog exists - see the content plan) or a native LinkedIn-first post
  when there's no matching blog piece yet.
- 1 lighter post - a changelog note, a relevant industry article with
  a genuine opinion attached (not just a share), or a question to the
  audience.
- Occasionally a third: a comparison-table or carousel post.

Better to post twice a week consistently than five times for two
weeks and go quiet - LinkedIn's own distribution rewards accounts it
can predict will keep posting.

## 4. Starting posts (ready to use or adapt)

Five drafts, one per pillar plus a launch post, written in the voice
documented in `docs/DatFe_Brand_Guidelines.docx` - plainspoken,
concrete, a little wry, never flippant about the real problem.

### Launch post

> We just put DatFe's pricing on a public page. All of it - no "contact sales" wall.
>
> Every catalog/governance tool in this space (Collibra, Atlan, Select Star, the rest) makes you talk to someone before you find out what it costs. We think that's backwards for a 20-300 person company trying to figure out if this is even worth evaluating.
>
> So: datafetech.com/pricing. Free tier included - one source, unlimited viewers, no credit card.
>
> If you've ever gotten a quote "sized for a platform team you don't have," we built this for you.

### "Who owns this?" pillar post

> A new analyst joins your team. Their first real task: pull a number for the exec team.
>
> They open the warehouse. There are three tables that could plausibly be "the" customer table. Two look stale. One has a name nobody explained. They post in Slack: "which customer table is the real one?"
>
> Forty minutes and six replies later, they have an answer - and a slightly worse first impression of how the company runs its data.
>
> This isn't a tooling problem you fix with more Slack channels. It's a documentation-doesn't-exist problem. That's the actual, boring, unglamorous thing a data catalog is for - and it's the whole reason we built DatFe.

### DPDP/GDPR pillar post (carousel intro text)

> "Do we have a PII inventory?" is a question every growing company eventually gets asked - by a customer's security review, a new compliance hire, or a regulator.
>
> Most small teams answer with a spreadsheet someone half-finished eight months ago.
>
> Here's what an actual, defensible PII inventory needs to cover (swipe) →

### Pricing differentiator pillar post

> We priced DatFe against what a real 20-50 person company would actually pay elsewhere. The gap surprised even us.
>
> [attach: comparison table image]
>
> Collibra: not viable below enterprise scale, sales-led, opaque pricing.
> Atlan: free for one person, then $25k-50k/yr once your actual team is on it.
> DatFe: $0-1,200/yr for most small teams, ~$4,200/yr covers most 20-50 person companies.
>
> Same category. Very different assumption about who you are.

### Product-led proof pillar post

> Someone on our team asked the DatFe Ask assistant "what's our most stale customer-facing table?" - not searched, asked, in plain English.
>
> It answered with the actual table, the actual last-scan date, and which dashboards depend on it - because it's grounded in the real catalog and lineage graph, not a canned FAQ.
>
> [attach: screenshot of the Ask conversation]
>
> This is the difference between a catalog you have to search correctly and one you can just ask.

## 5. Growth basics for a solo-operator page

- **Personal profile first**: your own posts (as Soumick) reach further early on than the Company Page's posts do - LinkedIn's algorithm favors personal accounts. Post from your profile, tag/mention the Company Page, and have the page repost/share it rather than treating the Company Page as the primary publishing account.
- **Employee association**: make sure your personal profile lists DatFe as your current position, linked to the Company Page - this is what populates the "employees" count and gives the page any credibility signal at all in its first months.
- **Comment on relevant posts** in the data/governance space (Atlan's, Select Star's, and others' posts, relevant hashtags like #datagovernance, #dataengineering) with genuine, specific comments - not "great post!" - before expecting inbound engagement on your own posts.
- **No follower buying, no engagement pods** - both violate LinkedIn's terms and produce an audience that doesn't convert; given the actual buyer here is a specific, findable job title, quality of following matters far more than count.
