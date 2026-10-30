"""The gold set, read once: tests/evals/questions.yaml.

questions.yaml --> ALL_QUESTIONS --> QUESTIONS  (the thresholds were tuned
                                                 on these)
                                 --> HELDOUT    (`heldout: true`; never
                                                 used for tuning)
"""

from pathlib import Path

import yaml

ALL_QUESTIONS = yaml.safe_load((Path(__file__).parent / "questions.yaml").read_text())
QUESTIONS = [q for q in ALL_QUESTIONS if not q.get("heldout", False)]
HELDOUT = [q for q in ALL_QUESTIONS if q.get("heldout", False)]
