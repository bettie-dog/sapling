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
)

# Mock for submitting from a mid-stack commit (github.pr-workflow=stack):
# the native stack is #42/#43/#44 and the submit scope covers only #42/#43
# (an amend of the middle commit). The stack must not be touched -- the
# submit only pushes and hints that #44 was not part of this submit.
# Commit hashes come in via the R5_* environment variables.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    prs = [
        (42, "one\n", os.environ["R5_PR42_HEAD"], "main"),
        (43, "two\n", os.environ["R5_PR43_OLD_HEAD"], "pr42"),
    ]
    for num, msg, head_oid, base in prs:
        pr_id = f"PR_id_{num}"
        github_server.expect_get_pr_details_request(num).and_respond(
            pr_id, head_ref_oid=head_oid, base_ref_name=base
        )
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

    github_server.expect_get_stack_request(42).and_respond(
        [stack_json(45, [42, 43, 44])]
    )

    github_server.expect_get_username_request().and_respond()
    github_server.expect_merge_into_branch(os.environ["R5_TIP"]).and_respond()

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
