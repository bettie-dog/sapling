# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2.

from sapling import extensions
from sapling.ext.github import github_gh_cli, submit
from sapling.ext.github.mock_utils import mock_run_git_command, MockGitHubServer
from sapling.ext.github.pull_request_body import title_and_body

# Mock for `sl pr submit` with github.pr-workflow=stack against a repo where
# the stacks REST API is unavailable (e.g. the public preview is not enabled,
# or GitHub Enterprise): the submit must still succeed with single-workflow
# topology (chained bases) and only warn about the failed stack link.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    github_server.expect_guess_next_pull_request_number().and_respond()

    prs = [
        (42, "one\n"),
        (43, "two\n"),
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

        github_server.expect_update_pr_request(
            pr_id, num, msg, base=None
        ).and_respond()

    github_server.expect_get_username_request().and_respond()

    head = "1a67244b0a776bfcc3be6bf811e98c993d78ce47"
    github_server.expect_merge_into_branch(head).and_respond()

    github_server.expect_get_stack_request(42).and_error(
        "HTTP 404: Not Found (https://api.github.com/repos/facebook/test_github_repo/stacks?pull_request=42)"
    )

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
