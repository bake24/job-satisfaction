from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Option:
    code: str
    text: dict[str, str]


@dataclass
class Question:
    code: str
    text: dict[str, str]
    options: list[Option]


@dataclass
class Department:
    code: str
    name: dict[str, str]
    contact_gate_text: dict[str, str] | None
    requires_contact_gate: bool
    asks_department_feedback: bool
    sticker_emoji: str | None
    sticker_file_id: str | None
    questions: list[Question]


class SurveyCatalog:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._departments: list[Department] = []
        self._load()

    def _load(self) -> None:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        deps: list[Department] = []
        for dep in raw["departments"]:
            questions: list[Question] = []
            for q in dep["questions"]:
                if "options" in q:
                    options = [Option(code=o["code"], text=o["text"]) for o in q["options"]]
                else:
                    scale_from = int(q.get("scale_from", 1))
                    scale_to = int(q.get("scale_to", 10))
                    options = [
                        Option(code=str(score), text={"en": str(score), "ru": str(score), "uz": str(score)})
                        for score in range(scale_from, scale_to + 1)
                    ]
                questions.append(Question(code=q["code"], text=q["text"], options=options))
            deps.append(
                Department(
                    code=dep["code"],
                    name=dep["name"],
                    contact_gate_text=dep.get("contact_gate_text"),
                    requires_contact_gate=dep.get("requires_contact_gate", False),
                    asks_department_feedback=dep.get("asks_department_feedback", True),
                    sticker_emoji=dep.get("sticker_emoji"),
                    sticker_file_id=dep.get("sticker_file_id"),
                    questions=questions,
                )
            )
        self._departments = deps

    @property
    def departments(self) -> list[Department]:
        return self._departments
