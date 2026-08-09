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

# Mock for appending a new commit on top of an already-linked stack
# (github.pr-workflow=stack): the new PR must be created with its base
# chained to the previous PR's head branch (NOT the trunk -- the
# expect_create_pr_request below fails the test if base is "main"), and it
# is appended to the existing stack via the /add endpoint. Commit hashes
# come from the PR42_HEAD / PR43_NEW_HEAD / PR45_HEAD environment variables
# set by the .t test.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    # An issue #44 makes the next guessed pull request number 45.
    github_server.expect_guess_next_pull_request_number().and_respond(
        latest_issue_num=44, latest_pr_num=43
    )

    existing = [
        (42, "one\n", os.environ["PR42_HEAD"], "main"),
        (43, "two\n", os.environ["PR43_NEW_HEAD"], "pr42"),
    ]
    for num, msg, head_oid, base in existing:
        pr_id = f"PR_id_{num}"
        github_server.expect_get_pr_details_request(num).and_respond(
            pr_id, head_ref_oid=head_oid, base_ref_name=base
        )
        github_server.expect_update_pr_request(pr_id, num, msg, base=None).and_respond()

    # The base being "pr43" (and not "main") is the point of this test.
    github_server.expect_create_pr_request(
        body="",
        title="three",
        head="pr45",
        base="pr43",
    ).and_respond(number=45)
    github_server.expect_get_pr_details_request(45).and_respond(
        "PR_id_45", base_ref_name="pr43"
    )
    github_server.expect_update_pr_request(
        "PR_id_45", 45, "three\n", base=None
    ).and_respond()

    github_server.expect_get_username_request().and_respond()

    github_server.expect_merge_into_branch(os.environ["PR45_HEAD"]).and_respond()

    github_server.expect_get_stack_request(42).and_respond(
        [stack_json(44, [42, 43])]
    )
    github_server.expect_add_to_stack_request(44, [45]).and_respond(
        stack_json(44, [42, 43, 45])
    )

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
