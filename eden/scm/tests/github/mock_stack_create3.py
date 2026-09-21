# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2.

import os

from sapling import extensions
from sapling.ext.github import github_gh_cli, submit
from sapling.ext.github.consts import GITHUB_HOSTNAME
from sapling.ext.github.mock_utils import (
    mock_run_git_command,
    MockGitHubServer,
    OWNER,
    REPO_NAME,
    stack_json,
)
from sapling.ext.github.pull_request_body import (
    _format_review_url,
    DEFAULT_REVIEW_TOOL_NAME,
    DEFAULT_REVIEW_URL_TEMPLATE,
    title_and_body,
)

# Like mock_stack_create, but for a three-commit stack: PRs #42/#43/#44 are
# created with chained bases and linked into native stack #45. The tip commit
# hash is passed in via the CREATE3_TIP environment variable.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    github_server.expect_guess_next_pull_request_number().and_respond()

    prs = [
        (42, "one\n"),
        (43, "two\n"),
        (44, "three\n"),
    ]

    for idx, (num, msg) in enumerate(prs):
        title, body = title_and_body(msg)
        head = f"pr{num}"

        base = "main"
        if idx > 0:
            base = "pr%d" % prs[idx - 1][0]

        github_server.expect_create_pr_request(
            body=body,
            title=title,
            head=head,
            base=base,
        ).and_respond(number=num)

        pr_id = f"PR_id_{num}"
        github_server.expect_get_pr_details_request(num).and_respond(pr_id)

        # No stack footer is rendered for the stack workflow, but the review
        # link arguments are required by expect_update_pr_request.
        github_server.expect_update_pr_request(
            pr_id,
            num,
            msg,
            base=None,
            review_url=_format_review_url(
                DEFAULT_REVIEW_URL_TEMPLATE,
                owner=OWNER,
                repo=REPO_NAME,
                number=num,
                hostname=GITHUB_HOSTNAME,
            ),
            review_tool=DEFAULT_REVIEW_TOOL_NAME,
        ).and_respond()

    github_server.expect_get_username_request().and_respond()

    github_server.expect_merge_into_branch(os.environ["CREATE3_TIP"]).and_respond()

    # Two-point discovery: with no stack found for the bottom PR, the top PR
    # is also queried before concluding no stack exists.
    github_server.expect_get_stack_request(42).and_respond([])
    github_server.expect_get_stack_request(44).and_respond([])
    github_server.expect_create_stack_request([42, 43, 44]).and_respond(
        stack_json(45, [42, 43, 44])
    )

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
