# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2.

"""native GitHub "stacked pull requests" support for `sl pr submit`.

Everything specific to GitHub's native stacks REST API (a public preview)
lives here: the API wrappers, stack discovery, and the reconciliation that
keeps the native stack mirroring the local stack of pull requests.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING, Union

from sapling import error
from sapling.i18n import _
from sapling.result import Err, Ok, Result

from . import gh_submit, github_gh_cli as gh_cli
from .gh_submit import PullRequestState, Repository
from .github_gh_cli import JsonDict
from .none_throws import none_throws

if TYPE_CHECKING:
    from .submit import CommitData

_Params = Union[str, int, bool, List[int], List[str]]

# The GitHub REST API version that includes the stacked pull requests
# endpoints. As of Aug 2026, stacked pull requests are a public preview
# feature: https://docs.github.com/en/pull-requests/reference/stacked-pull-requests
STACKS_API_VERSION = "2026-03-10"

_STACKS_HEADERS = {"X-GitHub-Api-Version": STACKS_API_VERSION}

GRAPHQL_GET_PR_OWNERSHIP = """
query GetPrOwnership($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      author {
        login
      }
      headRefName
    }
  }
}
"""

# Head branches that `sl pr submit` itself creates.
_SAPLING_PR_BRANCH = re.compile(r"^pr\d+$")


@dataclass
class PullRequestStackEntry:
    number: int
    # "open" or "closed" (a merged pull request is "closed" with merged_at
    # set); merged/closed pull requests remain members of their stack.
    state: str
    merged: bool
    # The list endpoint (GET /stacks?pull_request=N) returns minimal pull
    # request objects without a base (and potentially without a head), so
    # these are best-effort.
    base_branch_name: Optional[str]
    head_branch_name: Optional[str]


@dataclass
class PullRequestStack:
    """A native GitHub stack of pull requests, ordered bottom to top."""

    number: int
    base_branch_name: str
    is_open: bool
    entries: List[PullRequestStackEntry] = field(default_factory=list)

    def open_pr_numbers(self) -> List[int]:
        """Numbers of the open (unmerged, unclosed) members, bottom to top."""
        return [e.number for e in self.entries if e.state == "open"]

    def all_pr_numbers(self) -> List[int]:
        return [e.number for e in self.entries]


def _parse_stack(stack: JsonDict) -> PullRequestStack:
    return PullRequestStack(
        number=stack["number"],
        base_branch_name=stack["base"]["ref"],
        is_open=stack["open"],
        entries=[
            PullRequestStackEntry(
                number=pr["number"],
                state=pr["state"],
                merged=pr.get("merged_at") is not None,
                base_branch_name=(pr.get("base") or {}).get("ref"),
                head_branch_name=(pr.get("head") or {}).get("ref"),
            )
            for pr in stack["pull_requests"]
        ],
    )


async def get_stack_for_pull_request(
    hostname: str, owner: str, name: str, number: int
) -> Result[Optional[PullRequestStack], str]:
    """Returns the native GitHub stack containing the given pull request, or
    None if the pull request is not part of a stack.
    """
    endpoint = f"repos/{owner}/{name}/stacks"
    params: Dict[str, _Params] = {"pull_request": number}
    result = await gh_cli.make_request(
        params, hostname=hostname, endpoint=endpoint, method="GET",
        headers=_STACKS_HEADERS,
    )
    if result.is_err():
        return Err(result.unwrap_err())
    stacks = result.unwrap()
    if not stacks:
        return Ok(None)
    return Ok(_parse_stack(stacks[0]))


async def create_pull_request_stack(
    hostname: str, owner: str, name: str, pull_requests: List[int]
) -> Result[PullRequestStack, str]:
    """Links existing pull requests into a new native GitHub stack.

    pull_requests is ordered bottom to top. GitHub validates that each pull
    request's base branch is the head branch of the previous entry (and the
    bottom entry's base is the stack's trunk); it does not fix up bases, so
    the caller must ensure the chain holds before calling this.
    """
    endpoint = f"repos/{owner}/{name}/stacks"
    params: Dict[str, _Params] = {"pull_requests": pull_requests}
    result = await gh_cli.make_request(
        params, hostname=hostname, endpoint=endpoint, headers=_STACKS_HEADERS
    )
    if result.is_err():
        return Err(result.unwrap_err())
    return Ok(_parse_stack(result.unwrap()))


async def add_pull_requests_to_stack(
    hostname: str, owner: str, name: str, stack_number: int, pull_requests: List[int]
) -> Result[PullRequestStack, str]:
    """Appends pull requests to the top of an existing stack."""
    endpoint = f"repos/{owner}/{name}/stacks/{stack_number}/add"
    params: Dict[str, _Params] = {"pull_requests": pull_requests}
    result = await gh_cli.make_request(
        params, hostname=hostname, endpoint=endpoint, headers=_STACKS_HEADERS
    )
    if result.is_err():
        return Err(result.unwrap_err())
    return Ok(_parse_stack(result.unwrap()))


async def unstack_pull_requests(
    hostname: str, owner: str, name: str, stack_number: int, pull_requests: List[int]
) -> Result[None, str]:
    """Removes pull requests from a stack.

    Removing entries cascades aggressively: a stack can dissolve entirely
    even when more than one open member would remain, so callers must treat
    any unstack as potentially dissolving the whole stack and re-link every
    member they still want stacked.
    """
    endpoint = f"repos/{owner}/{name}/stacks/{stack_number}/unstack"
    params: Dict[str, _Params] = {"pull_requests": pull_requests}
    result = await gh_cli.make_request(
        params, hostname=hostname, endpoint=endpoint, headers=_STACKS_HEADERS
    )
    if result.is_err():
        return Err(result.unwrap_err())
    return Ok(None)


async def _get_stack_for_any(
    hostname: str, owner: str, name: str, numbers: List[int]
) -> Result:
    """Queries the stacks API for each pull request number in turn, returning
    the first stack found, Ok(None) if none of them is in a stack, or Err on
    the first API failure.
    """
    for number in numbers:
        result = await get_stack_for_pull_request(hostname, owner, name, number)
        if result.is_err() or result.unwrap() is not None:
            return result
    return Ok(None)


async def find_native_stack(
    partitions: List[List["CommitData"]], repository: Repository
) -> Result:
    """Returns Ok(PullRequestStack) for the native stack containing the local
    stack's pull requests, Ok(None) if there is no associated pull request or
    none is in a stack, or Err on API failure.

    Queries with the bottom-most existing pull request first (the most stable
    member of an existing stack), then the top-most, to catch stacks whose
    bottom was reordered or replaced locally.
    """
    # partitions is ordered from the top of the stack to the bottom.
    existing = [p[0].pr.number for p in reversed(partitions) if p[0].pr]
    candidates = list(dict.fromkeys([existing[0], existing[-1]])) if existing else []
    return await _get_stack_for_any(
        repository.hostname, repository.owner, repository.name, candidates
    )


def _classify_stack_divergence(
    desired: List[int], stack_open: List[int], has_new_prs: bool
) -> Tuple[str, List[int]]:
    """Compares the open members of the native stack against the open pull
    requests of the submit scope (both bottom to top).

    Returns (kind, off_path) where kind is one of:
    - "match": identical.
    - "append": the stack is a prefix of the scope (new members go on top).
    - "mid_stack": the scope is a prefix of the stack and nothing new is
      being created above it -- a submit from a mid-stack commit.
    - "rebuild": anything else -- the order of open members changed, or the
      stack has open members that are not part of the submit scope (a
      dropped/folded commit, or a different line of a forked tree).
      off_path lists those members.
    """
    if stack_open == desired:
        return ("match", [])
    if stack_open == desired[: len(stack_open)]:
        return ("append", [])
    if desired == stack_open[: len(desired)]:
        if has_new_prs:
            return ("rebuild", stack_open[len(desired) :])
        return ("mid_stack", [])
    return ("rebuild", [n for n in stack_open if n not in desired])


async def _get_pr_ownership(
    hostname: str, owner: str, name: str, number: int
) -> Result[Tuple[Optional[str], Optional[str]], str]:
    """Returns (author_login, head_ref_name) for the pull request."""
    params: Dict[str, _Params] = {
        "query": GRAPHQL_GET_PR_OWNERSHIP,
        "owner": owner,
        "name": name,
        "number": number,
    }
    result = await gh_cli.make_request(params, hostname=hostname)
    if result.is_err():
        return Err(result.unwrap_err())
    pr = result.unwrap()["data"]["repository"]["pullRequest"]
    author = (pr.get("author") or {}).get("login")
    return Ok((author, pr.get("headRefName")))


async def _abort_if_not_ours(
    off_path: List[int], repository: Repository, stack_number: int
) -> None:
    """Aborts unless every off-path open member of the stack is a pull
    request this checkout could have created: authored by the authenticated
    user, with a sapling-made pr<N> head branch.
    """
    if not off_path:
        return

    def query_failed(err: str) -> error.Abort:
        return error.Abort(
            _("cannot verify ownership of pull requests in native stack #%d: %s")
            % (stack_number, err)
        )

    username_result = await gh_submit.get_username(repository.hostname)
    if username_result.is_err():
        raise query_failed(username_result.unwrap_err())
    username = username_result.unwrap()

    foreign = []
    for number in off_path:
        ownership = await _get_pr_ownership(
            repository.hostname, repository.owner, repository.name, number
        )
        if ownership.is_err():
            raise query_failed(ownership.unwrap_err())
        author, head = ownership.unwrap()
        if author != username or not head or not _SAPLING_PR_BRANCH.match(head):
            foreign.append(number)
    if foreign:
        raise error.Abort(
            _(
                "cannot rebuild native stack #%d: it contains pull requests "
                "not created from this checkout (%s)"
            )
            % (stack_number, ", ".join(f"#{n}" for n in foreign)),
            hint=_("resolve this on GitHub (e.g. with 'gh stack unstack') and re-run"),
        )


async def _unstack_all_open(
    ui, stack: PullRequestStack, repository: Repository, rebuild: bool
) -> None:
    unstack_result = await unstack_pull_requests(
        repository.hostname,
        repository.owner,
        repository.name,
        stack.number,
        stack.open_pr_numbers(),
    )
    if unstack_result.is_err():
        # Pushing reordered branches while bases are locked risks GitHub
        # auto-closing PRs as "merged" (see #1275), so refuse to continue.
        raise error.Abort(
            _("cannot update pull request bases while they are in stack #%d: %s")
            % (stack.number, unstack_result.unwrap_err())
        )
    if rebuild:
        ui.status_err(_("dissolved native stack #%d for rebuild\n") % stack.number)
    else:
        ui.status_err(
            _("temporarily unstacked #%d to update pull request bases\n")
            % stack.number
        )


async def _retarget_bases(ui, mismatched, repository: Repository) -> None:
    for pr, base in mismatched:
        result = await gh_submit.update_pull_request(
            repository.hostname, pr.node_id, pr.title, pr.body, base
        )
        if result.is_err():
            ui.status_err(
                _("warning, updating base for #%d may not have succeeded: %s\n")
                % (pr.number, result.unwrap_err())
            )
        else:
            ui.status_err(_("updated base for %s\n") % pr.url)


async def prepare_native_stack_bases(
    ui,
    partitions: List[List["CommitData"]],
    trunk: str,
    repository: Repository,
    *,
    rebuild_stack: bool = False,
    has_new_prs: bool = False,
) -> None:
    """Reconciles the native GitHub stack with the submit scope BEFORE
    anything is pushed, retargeting the base branch of existing open PRs
    whose position in the local stack changed (base branches are locked
    while stacked, so this dissolves the stack first when needed; it is
    re-linked after the push by sync_native_stack()).

    Order-preserving changes (amends, appends, a commit inserted between two
    members) are handled automatically. Changes that reorder open members or
    leave open members of the stack outside the submit scope (a dropped or
    folded commit, or a different line of a forked tree) abort unless
    --rebuild-stack was passed: rebuilding rewrites reviewer-visible state.
    Stacks containing pull requests not created from this checkout are never
    modified.
    """
    mismatched = []
    for index, partition in enumerate(partitions):
        pr = partition[0].pr
        if not pr or pr.state != PullRequestState.OPEN:
            continue
        base = trunk
        if index < len(partitions) - 1:
            base = none_throws(partitions[index + 1][0].head_branch_name)
        if pr.base_branch_name != base:
            mismatched.append((pr, base))

    desired = [
        p[0].pr.number
        for p in reversed(partitions)
        if p[0].pr and p[0].pr.state == PullRequestState.OPEN
    ]
    if not desired:
        return

    stack = None
    stack_result = await find_native_stack(partitions, repository)
    if stack_result.is_err():
        ui.status_err(
            _("warning: could not query native stack state: %s\n")
            % stack_result.unwrap_err()
        )
    else:
        stack = stack_result.unwrap()

    if stack is None or not stack.is_open:
        await _retarget_bases(ui, mismatched, repository)
        return

    kind, off_path = _classify_stack_divergence(
        desired, stack.open_pr_numbers(), has_new_prs
    )
    if kind == "mid_stack":
        # Members above the submit scope keep their positions; nothing to
        # retarget (sync_native_stack prints the hint after the push).
        return
    if kind in ("match", "append"):
        if not mismatched:
            return
        # Order-preserving base changes (e.g. a commit inserted between two
        # stacked members): safe to dissolve silently; the stack is
        # re-linked after the push.
        await _unstack_all_open(ui, stack, repository, rebuild=False)
        await _retarget_bases(ui, mismatched, repository)
        return

    # kind == "rebuild"
    await _abort_if_not_ours(off_path, repository, stack.number)
    if not rebuild_stack:
        if off_path:
            raise error.Abort(
                _(
                    "native stack #%d contains open pull requests that are "
                    "not among the commits being submitted: %s"
                )
                % (stack.number, ", ".join(f"#{n}" for n in off_path)),
                hint=_(
                    "re-run with --rebuild-stack to rebuild the native stack "
                    "on this line (they stay open but leave the stack)"
                ),
            )
        raise error.Abort(
            _(
                "the local stack was reordered, so native stack #%d must be "
                "dissolved and re-created (GitHub locks pull request bases "
                "while stacked)"
            )
            % stack.number,
            hint=_("re-run with --rebuild-stack to do this automatically"),
        )
    await _unstack_all_open(ui, stack, repository, rebuild=True)
    if off_path:
        ui.status_err(
            _("%s left open and unstacked; close them on GitHub if no longer needed\n")
            % ", ".join(f"#{n}" for n in off_path)
        )
    await _retarget_bases(ui, mismatched, repository)


async def sync_native_stack(
    ui, partitions: List[List["CommitData"]], repository: Repository
) -> None:
    """Ensures the pull requests for `partitions` are linked into a native
    GitHub stack, bottom to top.

    Failures are reported as warnings rather than errors: by this point the
    pull requests already exist with chained bases (plain SINGLE-workflow
    topology), so linking can be retried on a future submit. This also serves
    as the fallback for repos where the stacks API (a public preview) is not
    available.
    """
    prs = [p[0].pr for p in partitions]
    non_open = [pr for pr in prs if pr and pr.state != PullRequestState.OPEN]
    if non_open:
        ui.status_err(
            _("not syncing native stack because #%d is not open\n")
            % non_open[0].number
        )
        return
    # Bottom to top, as the stacks API expects.
    desired = [pr.number for pr in reversed(prs) if pr]
    if len(desired) < 2:
        # A single pull request is not a stack.
        return

    hostname = repository.hostname
    owner = repository.owner
    name = repository.name

    def warn(err: str) -> None:
        ui.status_err(
            _(
                "warning: failed to sync native GitHub stack: %s\n"
                "pull requests remain chained and can be linked on a future submit\n"
            )
            % err
        )

    # Query with the bottom pull request first (the most stable member of an
    # existing stack), then the top, to catch stacks whose bottom was
    # reordered or replaced locally.
    result = await _get_stack_for_any(
        hostname, owner, name, [desired[0], desired[-1]]
    )
    if result.is_err():
        warn(result.unwrap_err())
        return
    stack = result.unwrap()

    if stack and stack.is_open:
        open_members = stack.open_pr_numbers()
        if open_members == desired:
            ui.status_err(_("native stack #%d is up-to-date\n") % stack.number)
            return
        if len(desired) < len(open_members) and desired == open_members[: len(desired)]:
            # Submit from a mid-stack commit: members above the submit scope
            # keep their positions and are left untouched.
            ui.status_err(
                _(
                    "native stack #%d unchanged; %d pull request(s) stacked "
                    "above #%d were not part of this submit\n"
                )
                % (stack.number, len(open_members) - len(desired), desired[-1])
            )
            return
        # Appending is only valid when the new entries chain onto the stack's
        # ACTUAL top member — GitHub validates each added pull request's base
        # against the head of the full member list, which includes closed and
        # merged members. A closed pull request sitting at the stack's tail
        # (e.g. the top PR of the stack was closed and re-minted under a new
        # number) makes every append 422 forever; the only correct move then
        # is dissolve-and-relink below.
        top_is_open = bool(stack.entries) and stack.entries[-1].state == "open"
        if top_is_open and open_members == desired[: len(open_members)]:
            to_add = desired[len(open_members) :]
            add_result = await add_pull_requests_to_stack(
                hostname, owner, name, stack.number, to_add
            )
            if add_result.is_err():
                warn(add_result.unwrap_err())
                return
            ui.status_err(
                _("added %d pull request(s) to native stack #%d\n")
                % (len(to_add), stack.number)
            )
            return
        # Only reconcile stacks we fully own: if the GitHub stack contains
        # open pull requests that are not part of the local stack (e.g., a
        # collaborator linked extra PRs with `gh stack link`), dissolving it
        # would destroy their intentional state.
        foreign = [n for n in open_members if n not in desired]
        if foreign:
            ui.status_err(
                _(
                    "warning: not modifying native stack #%d because it contains "
                    "pull requests not in your local stack: %s\n"
                )
                % (stack.number, ", ".join(f"#{n}" for n in foreign))
            )
            return
        # Membership or order changed in a way that cannot be expressed as an
        # append: dissolve and re-link.
        unstack_result = await unstack_pull_requests(
            hostname, owner, name, stack.number, open_members
        )
        if unstack_result.is_err():
            warn(unstack_result.unwrap_err())
            return

    create_result = await create_pull_request_stack(
        hostname, owner, name, desired
    )
    if create_result.is_err():
        warn(create_result.unwrap_err())
        return
    ui.status_err(
        _("created native stack #%d with %d pull requests\n")
        % (create_result.unwrap().number, len(desired))
    )
