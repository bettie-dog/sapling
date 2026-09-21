# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This software may be used and distributed according to the terms of the
# GNU General Public License version 2.

import os

from sapling import extensions
from sapling.ext.github import github_gh_cli, native_stacks, submit
from sapling.ext.github.consts import GITHUB_HOSTNAME
from sapling.ext.github.mock_utils import (
    mock_run_git_command,
    MockGitHubServer,
    OWNER,
    REPO_NAME,
    stack_json,
    USER_NAME,
)
from sapling.ext.github.pull_request_body import (
    _format_review_url,
    DEFAULT_REVIEW_TOOL_NAME,
    DEFAULT_REVIEW_URL_TEMPLATE,
    title_and_body,
)

# Mock for submitting a different line of a forked tree
# (github.pr-workflow=stack): the native stack is #42/#43, and the submit
# comes from a new commit forked off #42's commit, so #43 is an open stack
# member that is not among the commits being submitted. The ownership of #43
# is verified (authored by the authenticated user, sapling-made pr43 head).
# Without --rebuild-stack the submit must abort before pushing or creating
# anything; with the flag it dissolves stack #44, leaves #43 open and
# unstacked, creates the new PR #45 chained on #42, and links stack #46.
# Commit hashes come in via the R4_* environment variables.


def setup_mock_github_server(ui) -> MockGitHubServer:
    github_server = MockGitHubServer()

    github_server.expect_get_repository_request().and_respond()

    github_server.expect_guess_next_pull_request_number().and_respond(
        latest_issue_num=40, latest_pr_num=44
    )

    github_server.expect_get_pr_details_request(42).and_respond(
        "PR_id_42", head_ref_oid=os.environ["R4_PR42_HEAD"], base_ref_name="main"
    )

    github_server.expect_get_stack_request(42).and_respond_seq(
        [[stack_json(44, [42, 43])], []]
    )
    github_server.expect_get_stack_request(45).and_respond([])

    # Ownership check for the off-path member #43.
    github_server.expect_get_username_request().and_respond()
    github_server.expect_request(
        params={
            "query": native_stacks.GRAPHQL_GET_PR_OWNERSHIP,
            "owner": OWNER,
            "name": REPO_NAME,
            "number": 43,
        },
        response={
            "data": {
                "repository": {
                    "pullRequest": {
                        "author": {"login": USER_NAME},
                        "headRefName": "pr43",
                    }
                }
            }
        },
    )

    github_server.expect_unstack_request(44, [42, 43]).and_respond({})

    title, body = title_and_body("four\n")
    github_server.expect_create_pr_request(
        body=body,
        title=title,
        head="pr45",
        base="pr42",
    ).and_respond(number=45)
    github_server.expect_get_pr_details_request(45).and_respond(
        "PR_id_45", base_ref_name="pr42"
    )

    for num, msg in ((42, "one\n"), (45, "four\n")):
        # No stack footer is rendered for the stack workflow, but the review
        # link arguments are required by expect_update_pr_request.
        github_server.expect_update_pr_request(
            f"PR_id_{num}",
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

    github_server.expect_create_stack_request([42, 45]).and_respond(
        stack_json(46, [42, 45])
    )

    github_server.expect_merge_into_branch(os.environ["R4_TIP"]).and_respond()

    return github_server


def uisetup(ui):
    mock_github_server = setup_mock_github_server(ui)
    extensions.wrapfunction(
        github_gh_cli, "_make_request", mock_github_server.make_request
    )
    extensions.wrapfunction(submit, "run_git_command", mock_run_git_command)
