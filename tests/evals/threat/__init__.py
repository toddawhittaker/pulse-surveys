"""SPEC §9.3's threat and self-harm floor: the slot, held open for E10.

E2-12's scope: "the threat/self-harm floor's *slot* exists in the structure with
no set and no number — setting it is E10's". Since E6 the typed threat and
self-harm cases live in `cases.py` here and are joined into the moderation set
(`tests/evals/moderation/cases.py`); they are not attached to the slot, which
stays deferred with no cases until E10 sets its floor. What this package proves
is that the structure accepts a task the runner cannot grade yet without either
inventing a number or passing over it in silence.
"""
