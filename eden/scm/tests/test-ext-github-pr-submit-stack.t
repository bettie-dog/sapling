#require git no-eden no-windows

  $ eagerepo
  $ enable github amend rebase
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

stack whose top member is a closed pull request (#60, e.g. closed and
re-minted under a new number): the open members are a prefix of the local
stack, but appending onto a closed top can never pass GitHub's base-ref
validation -- dissolve and re-link instead

  $ sl pr submit --config extensions.pr_submit_stack_closed_tail=$TESTDIR/github/mock_stack_closed_tail.py
  #42 is up-to-date
  #43 is up-to-date
  #45 is up-to-date
  no pull requests to update
  created native stack #46 with 3 pull requests

stack containing a pull request that is not ours (#99) besides having a
diverged order: never modified, only a warning

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

reordering the local stack: the submit aborts before pushing anything, and
--rebuild-stack dissolves the stack, retargets the bases, pushes, and
re-creates the stack in the new order

  $ cd ..
  $ sl init --git repo3
  $ cd repo3
  $ echo a > a1
  $ sl ci -Aqm one
  $ echo a >> a1
  $ sl ci -Aqm two
  $ echo c > c1
  $ sl ci -Aqm three
  $ export CREATE3_TIP=`sl log -r . -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_create3=$TESTDIR/github/mock_stack_create3.py
  pushing 3 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/42
  created new pull request: https://github.com/facebook/test_github_repo/pull/43
  created new pull request: https://github.com/facebook/test_github_repo/pull/44
  updated body for https://github.com/facebook/test_github_repo/pull/44
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  created native stack #45 with 3 pull requests
  $ export R3_PR43_OLD_HEAD=`sl log -r 'desc(two)' -T '{node}'`
  $ export R3_PR44_OLD_HEAD=`sl log -r 'desc(three)' -T '{node}'`
  $ sl rebase -qr 'desc(three)' -d 'desc(one)'
  $ sl rebase -qr 'desc(two)' -d 'desc(three)'
  $ sl goto -q 'desc(two)'
  $ export R3_PR42_HEAD=`sl log -r '.^^' -T '{node}'`
  $ export R3_TIP=`sl log -r . -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_reorder=$TESTDIR/github/mock_stack_reorder.py
  #42 is up-to-date
  abort: the local stack was reordered, so native stack #45 must be dissolved and re-created (GitHub locks pull request bases while stacked)
  (re-run with --rebuild-stack to do this automatically)
  [255]
  $ sl pr submit --rebuild-stack --config extensions.pr_submit_stack_reorder2=$TESTDIR/github/mock_stack_reorder.py
  #42 is up-to-date
  dissolved native stack #45 for rebuild
  updated base for https://github.com/facebook/test_github_repo/pull/43
  updated base for https://github.com/facebook/test_github_repo/pull/44
  pushing 2 to https://github.com/facebook/test_github_repo.git
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/44
  updated body for https://github.com/facebook/test_github_repo/pull/42
  created native stack #46 with 3 pull requests

submitting a different line of a forked tree: the stack follows one line at
a time, so the submit aborts (before creating or pushing anything) while an
open stack member is not among the commits being submitted; --rebuild-stack
moves the stack to the submitted line, leaving that member open but
unstacked

  $ cd ..
  $ sl init --git repo4
  $ cd repo4
  $ echo a > a1
  $ sl ci -Aqm one
  $ echo a >> a1
  $ sl ci -Aqm two
  $ sl pr submit --config extensions.pr_submit_stack_create4=$TESTDIR/github/mock_stack_create.py
  pushing 2 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/42
  created new pull request: https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  created native stack #44 with 2 pull requests
  $ export R4_PR42_HEAD=`sl log -r 'desc(one)' -T '{node}'`
  $ sl goto -q 'desc(one)'
  $ echo d > d1
  $ sl ci -Aqm four
  $ export R4_TIP=`sl log -r . -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_fork=$TESTDIR/github/mock_stack_fork.py
  #42 is up-to-date
  abort: native stack #44 contains open pull requests that are not among the commits being submitted: #43
  (re-run with --rebuild-stack to rebuild the native stack on this line (they stay open but leave the stack))
  [255]
  $ sl pr submit --rebuild-stack --config extensions.pr_submit_stack_fork2=$TESTDIR/github/mock_stack_fork.py
  #42 is up-to-date
  dissolved native stack #44 for rebuild
  #43 left open and unstacked; close them on GitHub if no longer needed
  pushing 1 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/45
  updated body for https://github.com/facebook/test_github_repo/pull/45
  updated body for https://github.com/facebook/test_github_repo/pull/42
  created native stack #46 with 2 pull requests

submitting from a mid-stack commit: the stack is not touched, the submit
only pushes its scope and hints about the members above it

  $ cd ..
  $ sl init --git repo5
  $ cd repo5
  $ echo a > a1
  $ sl ci -Aqm one
  $ echo a >> a1
  $ sl ci -Aqm two
  $ echo c > c1
  $ sl ci -Aqm three
  $ export CREATE3_TIP=`sl log -r . -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_create5=$TESTDIR/github/mock_stack_create3.py
  pushing 3 to https://github.com/facebook/test_github_repo.git
  created new pull request: https://github.com/facebook/test_github_repo/pull/42
  created new pull request: https://github.com/facebook/test_github_repo/pull/43
  created new pull request: https://github.com/facebook/test_github_repo/pull/44
  updated body for https://github.com/facebook/test_github_repo/pull/44
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  created native stack #45 with 3 pull requests
  $ export R5_PR42_HEAD=`sl log -r 'desc(one)' -T '{node}'`
  $ sl goto -q 'desc(two)'
  $ export R5_PR43_OLD_HEAD=`sl log -r . -T '{node}'`
  $ echo z > z1
  $ sl add -q z1
  $ sl amend
  hint[amend-restack]: descendants of * are left behind - use 'sl restack' to rebase them (glob)
  hint[hint-ack]: use 'sl hint --ack amend-restack' to silence these hints
  $ export R5_TIP=`sl log -r . -T '{node}'`
  $ sl pr submit --config extensions.pr_submit_stack_midstack=$TESTDIR/github/mock_stack_midstack.py
  #42 is up-to-date
  pushing 1 to https://github.com/facebook/test_github_repo.git
  updated body for https://github.com/facebook/test_github_repo/pull/43
  updated body for https://github.com/facebook/test_github_repo/pull/42
  native stack #45 unchanged; 1 pull request(s) stacked above #43 were not part of this submit
