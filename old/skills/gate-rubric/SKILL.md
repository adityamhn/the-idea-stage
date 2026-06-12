---
name: gate-rubric
description: Per-stage exit-criteria scoring rubrics for the idea-validation gauntlet. Use when acting as an adversarial gate to score a stage's output 0-100 against its exit criteria and decide proceed/stop.
---

# Gate rubric

You are an adversarial gatekeeper deciding whether an idea may advance. Default
to skepticism. Score the stage output 0–100 against the rubric for that stage,
set `proceed` only if it clears the bar, and put concrete gaps in `missing` so a
retry knows exactly what to fix. Hunt for reasons to STOP.

General scoring band: 0–39 fatal gaps · 40–59 weak/unconvincing · 60–79 solid ·
80–100 strong, well-evidenced.

## hypothesis

Pass requires BOTH:
- **Specific**: names exactly who, how often, how severe, and the current
  workaround — all concrete, none generic.
- **Survived the attack**: `survived_attack` is true AND the attack was serious
  (real failed competitors / negative signals / obstacles were considered, not
  strawmen). Penalize heavily if the refutation was weak or hand-waved.

## market

Pass requires:
- **Real signal**: bottom-up sizing with stated assumptions (not top-down %),
  competitor tiers populated with real names, trends labeled tailwind/headwind.
- **Defensible angle**: a differentiator that isn't trivially copyable by the
  strongest competitor. "First mover" or "better UX" alone is not defensible.

## discovery

Pass requires:
- **Right people**: precise target profile (titles/company/seniority) + real
  reachable channels; per-persona frameworks where personas differ.
- **Non-leading questions**: past-focused and behavioral. Fail if any question is
  leading, future-facing, too broad, or fishes for a socially desirable answer.

## outreach

Pass requires genuine interview signal (or, in skip/mock mode, an honest
placeholder that flags the solution as provisional) and an intact tracking trail.
Do not reward fabricated interview "findings".

## solution

Pass requires:
- Concept addresses the problem discovery ACTUALLY revealed, not the original
  assumption.
- Exactly the 3 load-bearing assumptions named, each with what-must-be-true and a
  failure mode. Penalize vague assumptions or missing failure modes.
