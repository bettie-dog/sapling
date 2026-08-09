# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2.

import os

from sapling import extensions
from sapling.ext.github import github_gh_cli, submit
from sapling.ext.github.mock_utils import (
    mock_run_git_command,
    MockGitHubServer,
    stack_json,
)

# Mock for re-submitting an already-linked stack after amending the top
# commit (github.pr-workflow=stack): the bottom PR is up-to-date, the top
# branch is force-pushed, no base is retargeted (bases still match, so the
# native stack is never dissolved), and the existing stack #44 is recognized
# as up-to-date. Commit hashes are passed in from the .t test via the
# PR42_HEAD / PR43_OLD_HEAD / PR43_NEW_HEAD environment variables.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    prs = [
        (42, "one\n", os.environ["PR42_HEAD"], "main"),
        (43, "two\n", os.environ["PR43_OLD_HEAD"], "pr42"),
    ]

    for num, msg, head_oid, base in prs:
        pr_id = f"PR_id_{num}"
        github_server.expect_get_pr_details_request(num).and_respond(
            pr_id, head_ref_oid=head_oid, base_ref_name=base
        )
        github_server.expect_update_pr_request(
            pr_id, num, msg, base=None, stack_pr_ids=[pr[0] for pr in prs]
        ).and_respond()

    github_server.expect_get_username_request().and_respond()

    github_server.expect_merge_into_branch(os.environ["PR43_NEW_HEAD"]).and_respond()

    github_server.expect_get_stack_request(42).and_respond(
        [stack_json(44, [42, 43])]
    )

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
