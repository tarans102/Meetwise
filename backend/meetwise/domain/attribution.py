"""Organisation-aware task classification. Deterministic, so it is easy to test.

Categories (relative to the current user):
  direct        assigned to the user
  team          assigned to someone who reports to the user
  dependency    assigned to someone else, but it names the user or overlaps their remit
  uncertain     no clear owner, or the owner cannot be resolved
  not_relevant  assigned to someone else with no visible link to the user
"""

from __future__ import annotations

from meetwise.domain.models import ActionItem
from meetwise.domain.org import OrgContext
from meetwise.textutils import token_overlap


def classify_action_item(
    item: ActionItem, org: OrgContext, utterance_text: dict[str, str]
) -> None:
    user = org.user
    if user is None or item.assignee is None:
        item.category = "uncertain"
        return

    person = org.resolve(item.assignee)
    if person is None:
        item.category = "uncertain"
        return

    if person.id == user.id:
        item.category = "direct"
        return
    if person.id in org.subordinates(user.id):
        item.category = "team"
        return

    evidence = " ".join(utterance_text.get(i, "") for i in item.evidence_ids)
    haystack = " ".join([item.description, *item.dependencies, evidence])
    remit = " ".join([*user.responsibilities, *user.ownership])
    if org.mentions_user(haystack) or (
        remit and token_overlap(item.description, remit) >= 0.4
    ):
        item.category = "dependency"
    else:
        item.category = "not_relevant"
