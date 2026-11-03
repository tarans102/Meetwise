"""Organisational context: the current user, their team, and name resolution."""

from __future__ import annotations

from dataclasses import dataclass, field

from meetwise.textutils import contains_phrase, normalize_name


@dataclass
class Person:
    id: str
    name: str
    designation: str = ""
    responsibilities: list[str] = field(default_factory=list)
    ownership: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    manager_id: str | None = None
    is_user: bool = False

    def names(self) -> list[str]:
        return [self.name, *self.aliases]


class OrgContext:
    def __init__(self, people: list[Person]) -> None:
        self.people = list(people)
        self._by_id = {p.id: p for p in self.people}
        self._name_index: dict[str, set[str]] = {}
        for person in self.people:
            for name in person.names():
                key = normalize_name(name)
                if key:
                    self._name_index.setdefault(key, set()).add(person.id)
        self.user: Person | None = next((p for p in self.people if p.is_user), None)

    def resolve(self, name: str | None) -> Person | None:
        """Exact, normalised match on a name or alias. Ambiguous names resolve to None."""
        if not name:
            return None
        ids = self._name_index.get(normalize_name(name), set())
        if len(ids) == 1:
            return self._by_id[next(iter(ids))]
        return None

    def subordinates(self, person_id: str) -> set[str]:
        found: set[str] = set()
        frontier = [person_id]
        while frontier:
            current = frontier.pop()
            for person in self.people:
                if person.manager_id == current and person.id not in found:
                    found.add(person.id)
                    frontier.append(person.id)
        return found

    def mentions_user(self, text: str) -> bool:
        if self.user is None:
            return False
        return any(contains_phrase(text, name) for name in self.user.names())

    def prompt_block(self) -> str:
        if not self.people:
            return "No organisational profile configured."
        lines = []
        for p in self.people:
            manager = (
                self._by_id[p.manager_id].name
                if p.manager_id in self._by_id
                else "none"
            )
            tag = " (current user)" if p.is_user else ""
            lines.append(
                f"- {p.name}{tag}; role: {p.designation or 'n/a'}; "
                f"aliases: {', '.join(p.aliases) or 'none'}; reports to: {manager}"
            )
        return "\n".join(lines)
