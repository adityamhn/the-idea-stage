"""The founders-playbook truth, in one place.

These constants are the product's backbone: the Idea-stage goal, the three exit
criteria, and the three traps. They are injected into the Coach (and surfaced in
onboarding by the frontend) so the whole app teaches and obeys the same playbook.
"""

from __future__ import annotations

# The single goal of the Idea stage.
GOAL = (
    "Research-oriented validation: assemble solid evidence that a real problem "
    "exists — and that the proposed solution actually addresses it — BEFORE "
    "committing resources to building. The ultimate question is: is this worth "
    "building?"
)

# The three exit-criteria questions. You leave the Idea stage when all three are
# a confident yes.
EXIT_CRITERIA = [
    (
        "Is the problem real and specific?",
        "You can name exactly who experiences it, how often, how severely it "
        "affects them, and what they currently do about it.",
    ),
    (
        "Does your solution address the ACTUAL problem?",
        "Not the problem you originally assumed — the one validation revealed. "
        "Sometimes they are the same; often they are not.",
    ),
    (
        "Do you have enough signal to justify building?",
        "Never certainty — but enough qualitative evidence that committing to an "
        "MVP is a reasoned decision rather than an act of faith.",
    ),
]

# The three traps the app actively guards against. Keyed so the Coach can flag a
# stage output against a specific principle.
TRAPS = {
    "building-vs-validating": (
        "Mistaking building for validating. A working prototype is not evidence "
        "that you solve a real problem — conversations with real people are. The "
        "prototype is a prop for those conversations, not a substitute for them."
    ),
    "premature-scaling": (
        "Premature scaling. When building is effortless, it is easy to scale "
        "execution far ahead of validated problem-solution fit. Keep sense-making "
        "ahead of building."
    ),
    "loss-of-objectivity": (
        "Loss of objectivity. Ask AI to support what you already believe and it "
        "will. Confirmation bias now comes with a research engine. The antidote is "
        "pointing the same rigor at refuting the idea."
    ),
}

TRAP_KEYS = tuple(TRAPS.keys())


def playbook_brief() -> str:
    """A compact text block for injecting the playbook into agent prompts."""
    criteria = "\n".join(
        f"  {i + 1}. {q} — {why}" for i, (q, why) in enumerate(EXIT_CRITERIA)
    )
    traps = "\n".join(f"  - {key}: {text}" for key, text in TRAPS.items())
    return (
        f"IDEA-STAGE GOAL\n{GOAL}\n\n"
        f"EXIT CRITERIA (all three must be a confident yes)\n{criteria}\n\n"
        f"TRAPS TO GUARD AGAINST\n{traps}"
    )
