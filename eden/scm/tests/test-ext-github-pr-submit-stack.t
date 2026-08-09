#require git no-eden no-windows

  $ eagerepo
  $ enable github amend
  $ export SL_TEST_GH_URL=https://github.com/facebook/test_github_repo.git
  $ . $TESTDIR/git.sh
  $ setconfig github.pr-workflow=stack

build up a github repo

  $ sl init --git repo1
  $ cd repo1
  $ echo a > a1
  $ sl ci -Aqm one
  $ echo a >> a1
  $ sl ci -Aqm two

confirm it is a 'github_repo'
  $ sl log -r. -T '{github_repo}\n'
  True

first submit: PRs are created with chained bases and linked into a native
GitHub stack

  $ sl pr submit --config extensions.pr_submit_stack_create=$TESTDIR/github/mock_stack_create.py
  pushing 2 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/42
  created new pull request: https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  created native stack #44 with 2 pull requests

amend the top commit and resubmit: only the top branch is pushed, no base is
retargeted (the mock rejects any updatePullRequest that carries baseRefName),
and the existing stack is recognized as up-to-date

  $ export PR42_HEAD=`sl log -r '.^' -T '{node}'`
  $ export PR43_OLD_HEAD=`sl log -r '.' -T '{node}'`
  $ echo b >> a1
  $ sl amend
  $ export PR43_NEW_HEAD=`sl log -r '.' -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_resubmit=$TESTDIR/github/mock_stack_resubmit.py
  #42 is up-to-date
  pushing 1 to https://github.com/facebook/test_github_repo.git
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  native stack #44 is up-to-date

append a new commit on top: the new PR is created with its base chained to
the previous PR's head branch (not the trunk) and appended to the existing
stack via the /add endpoint

  $ echo c > c1
  $ sl ci -Aqm three
  $ export PR45_HEAD=`sl log -r '.' -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_append=$TESTDIR/github/mock_stack_append.py
  #42 is up-to-date
  #43 is up-to-date
  pushing 1 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/45
  updated body for https://github.com/facebook/test_github_repo/pull/45
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  added 1 pull request(s) to native stack #44

no-op submit still reconciles the stack: with nothing to push, a previously
failed stack link is retried (two-point discovery queries the bottom and top
PRs before concluding no stack exists)

  $ sl pr submit --config extensions.pr_submit_stack_linknoop=$TESTDIR/github/mock_stack_linknoop.py
  #42 is up-to-date
  #43 is up-to-date
  #45 is up-to-date
  no pull requests to update
  created native stack #46 with 3 pull requests

diverged stack whose members are all ours: automatically dissolved and
re-linked to match the local stack

  $ sl pr submit --config extensions.pr_submit_stack_restack=$TESTDIR/github/mock_stack_restack.py
  #42 is up-to-date
  #43 is up-to-date
  #45 is up-to-date
  no pull requests to update
  created native stack #46 with 3 pull requests

stack containing a pull request that is not ours (#99): never modified, only
a warning

  $ sl pr submit --config extensions.pr_submit_stack_foreign=$TESTDIR/github/mock_stack_foreign.py
  #42 is up-to-date
  #43 is up-to-date
  #45 is up-to-date
  no pull requests to update
  warning: not modifying native stack #44 because it contains pull requests not in your local stack: #99

stacks API unavailable (e.g. preview not enabled): submit still succeeds with
chained bases and only warns

  $ cd ..
  $ sl init --git repo2
  $ cd repo2
  $ echo a > a1
  $ sl ci -Aqm one
  $ echo a >> a1
  $ sl ci -Aqm two
  $ sl pr submit --config extensions.pr_submit_stack_fallback=$TESTDIR/github/mock_stack_fallback.py
  pushing 2 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/42
  created new pull request: https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  warning: failed to sync native GitHub stack: HTTP 404: Not Found (https://api.github.com/repos/facebook/test_github_repo/stacks?pull_request=42)
  pull requests remain chained and can be linked on a future submit
