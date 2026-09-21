import {Command} from '@site/elements'

# Sapling stack

Sapling comes with a [`pr` subcommand](/docs/commands/pr.md) to help you work with GitHub pull requests.

Once you have a stack of commits, you can use <Command name="pr" linkText="sl pr submit --stack" /> (or `sl pr s -s`) to create a pull request for each commit in the stack, or to update existing pull requests linked to the commits.

:::caution

Make sure you have followed the instructions to [authenticate with GitHub using the GitHub CLI `gh`](/docs/introduction/getting-started.md#authenticating-with-github) before using `sl pr`.

:::

:::caution

By default, `sl pr submit` creates _overlapping_ pull requests where each pull request contains the commit that is intended to be reviewed as part of the pull request as well as all commits below it in the stack. This will not "look right" on GitHub, so collaborators who use this command are encouraged to use [ReviewStack](/docs/addons/reviewstack.md) to review these pull requests, as ReviewStack will present only the commit that is intended to be reviewed for each pull request. Alternatively, see [Pull request workflows](#pull-request-workflows) below for the `stack` workflow, which uses GitHub's native support for stacked pull requests.

:::

## Pull request workflows

The `github.pr-workflow` config option controls how `sl pr submit` maps a stack of commits onto pull requests:

- `overlap` (default): every pull request targets the repository's default branch, so each pull request contains its commit plus all commits below it in the stack. Best reviewed with [ReviewStack](/docs/addons/reviewstack.md).
- `single`: each pull request contains exactly one commit and targets the head branch of the pull request below it in the stack, so each pull request shows only the diff for its own commit.
- `stack`: like `single`, but the pull requests are also linked together using GitHub's native [stacked pull requests](https://docs.github.com/en/pull-requests/get-started/about-stacked-prs) feature (public preview), so GitHub renders the stack map in the pull request UI and merges from the bottom up.

To enable the native stack workflow:

```
sl config --user github.pr-workflow stack
```

Notes on the `stack` workflow:

- GitHub requires all branches of a stack to live in the same repository, so pull requests are created against the push remote's repository itself rather than its upstream. If your push remote is a fork, the stack lives on the fork.
- Amending commits, appending new ones, and re-linking after an earlier failure are handled automatically. Changes that would rewrite the stack's reviewer-visible shape — reordering commits, dropping or folding a commit whose pull request is still open, or submitting a different line of a forked tree — make `sl pr submit` stop before pushing anything; re-run it with `--rebuild-stack` to dissolve the stack, retarget the bases, and re-link it to match. Pull requests that fall out of the stack this way stay open (with their chained base) but leave the stack; close them on GitHub if they are no longer needed.
- GitHub's native stacks are strictly linear and a pull request can belong to only one stack, so a forked local tree can have pull requests on every line but a native stack on only one line at a time; `--rebuild-stack` moves the stack to the line being submitted.
- Stacks containing pull requests that were not created from your checkout (e.g. linked by a collaborator with `gh stack link`) are never modified, with or without `--rebuild-stack`; resolve those on GitHub.
- Submitting from a mid-stack commit updates just the pull requests in scope and leaves the stack untouched, with a hint about the members above.
- If linking the stack fails (for example, the stacks API preview is not enabled for the repository), the pull requests are still created with chained bases and a warning is printed; re-running `sl pr submit` retries the link.
- Pull requests created with this workflow omit the "Stack created with Sapling" footer from their descriptions, since GitHub displays the stack natively.

If you get into a funny state, try using `sl pr link` or `sl pr unlink` to add or remove associations between commits and pull requests, as appropriate.
