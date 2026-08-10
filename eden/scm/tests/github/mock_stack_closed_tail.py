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

# Mock for `sl pr submit` (github.pr-workflow=stack) where the GitHub stack's
# TOP member (#60) is a closed pull request that is no longer in the local
# stack (e.g. the top PR was closed and re-minted under a new number). The
# open members ([42, 43]) are a prefix of the local stack ([42, 43, 45]), but
# appending #45 can never succeed: GitHub validates the added pull request's
# base against the head of the full member list, which is the closed #60 --
# every append 422s forever. Submit must dissolve and re-link instead.


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
        [stack_json(44, [42, 43, 60], closed=[60])]
    )
    # Only the open members are unstacked; the closed #60 stays behind as
    # closed-stack history and the cascade dissolves the stack.
    github_server.expect_unstack_request(44, [42, 43]).and_respond({})
    github_server.expect_create_stack_request([42, 43, 45]).and_respond(
        stack_json(46, [42, 43, 45])
    )

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
