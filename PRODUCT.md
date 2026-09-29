# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Confirmed by the approved implementation plan: Flask serves a no-build HTML, CSS, and vanilla JavaScript interface. The production target is GitHub plus Render, with PostgreSQL persistence on Supabase.

## Users

The primary user wants to enter two football teams and a kickoff time, then receive one evidence-backed pre-match analysis without manually collecting odds or filling technical fields.

## Product Purpose

The product resolves the fixture, gathers free live evidence, runs the quantitative research model, and explains the result in Chinese with source links. Success means the user can understand the probabilities, missing evidence, market limitations, and current no-bet status from one request.

## Positioning

The system separates evidence collection, quantitative probability, Asian-handicap settlement, and AI explanation. Every conclusion remains tied to timestamped source material, while missing data stays visibly missing.

## Operating Context

The user typically checks a future match on mobile or desktop before kickoff. The only required inputs are home team, away team, and local kickoff time. The system may ask the user to choose between fixture candidates only when names are ambiguous.

## Capabilities and Constraints

- Automatically resolves fixtures and gathers team context, injuries, weather, news, lineups, and available Asian-handicap prices from free legal sources.
- Uses a separately configured ailindo gateway and model. It must not silently fall back to an older model.
- Keeps `NO_BET_UNVALIDATED` until the strict forward-validation gate passes.
- Never synthesizes missing odds, betting volume, injuries, lineups, or news.
- Free infrastructure may sleep or enforce quotas, so loading and degraded states are part of the product.

## Brand Commitments

The user approved the “match-night intelligence room” direction: football atmosphere, deep stadium greens, warm floodlight energy, meaningful scan motion, and a polished experience that feels inviting rather than clinical. The interface must remain in Chinese and must not resemble a generic dashboard.

## Evidence on Hand

- Existing v8 research model and validation report live outside the deployable repository under `model/v8`.
- The independent pressure test is promising but statistically inconclusive; it cannot support a profitability claim.
- Official source research notes are stored under `docs/research/`.
- No licensed hero photography or finished brand logo was supplied. Future work must not fabricate commercial proof, customers, or accuracy claims.

## Product Principles

1. Three inputs in, evidence-backed report out.
2. Missing truth is better than invented certainty.
3. Quantitative output remains independent from AI prose.
4. No-bet is a valid and often preferred result.
5. Every visible claim should be understandable and auditable.

## Accessibility & Inclusion

Mobile-first responsive behavior, keyboard access, clear focus states, 44px touch targets, readable Chinese copy, non-color-only status cues, and reduced-motion support are required.
