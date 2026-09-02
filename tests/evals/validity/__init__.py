"""SPEC §3.3's comment-validity task: the eval set and the floor that gates on it.

`cases.py` holds the set; `floors.py` holds the numbers and the sentence saying
how they were picked. They sit in one directory on purpose — SPEC §9.3's floors
are only meaningful against the set they were measured over, and a floor moved in
a shared file two directories away is a change a reviewer reads without the set
in front of them.
"""
