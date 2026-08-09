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

# Mock for a no-op `sl pr submit` (github.pr-workflow=stack) where the stack
# on GitHub contains a pull request (#99) that is not part of the local stack
# (e.g. a collaborator linked it with `gh stack link`): submit must not
# dissolve or otherwise modify the stack -- it only warns. The absence of
# unstack/create expectations makes any modification attempt fail the test.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    prs = [
        (42, os.environ["PR42_HEAD"], "main"),
        (43, os.environ["PR43_NEW_HEAD"], "pr42"),
        (45, os.environ["PR45_HEAD"], "pr43"),
    ]
    for num, head_oid, base in prs:
        github_server.expect_get_pr_details_request(num).and_respond(
            f"PR_id_{num}", head_ref_oid=head_oid, base_ref_name=base
        )

    github_server.expect_get_stack_request(42).and_respond(
        [stack_json(44, [42, 43, 45, 99])]
    )

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
