# The tool that makes `tint-only`

This branch holds one tool and the list it applies. **`tint-only`, the default branch of this fork,
is Dawn with everything Tint's build does not read deleted**, and nothing on it is authored here:
each of its commits is an upstream commit of `dawn.googlesource.com` with paths removed. That is why
the tool lives on a branch of its own. Plain git answers where a trimmed commit came from —

```sh
git diff --name-status --no-renames <upstream> <trimmed>     # every line is a D
```

— and the tool is what makes such a commit and checks more than that line can.

| File | What it is |
| --- | --- |
| `kept` | what a trimmed commit keeps of the upstream commit: three directories, eight files, three gitlinks |
| `tint_only.py` | `init`, `sync`, `verify`, `test` |
| `tint_only_cases.py` | the cases that hold each refusal, on repositories built for the purpose |

It needs Python 3.10 or newer and git, and nothing else.

## A roll

A roll is made when something that builds from this fork needs a fix upstream has, and not to stay
current. It is asked for by one of Dawn's release tags, which `github.com/google/dawn` cuts on
weekday nights; the commit a tag names is fetched from `dawn.googlesource.com`.

```sh
python3 tint_only.py sync v20261002.154047    # build the commit, check it, move the local branch
python3 tint_only.py verify                   # check it again, on its own
git push origin tint-only                     # nothing above pushes
```

Then the consumer moves its pin to the new commit, and its own build says whether Tint configures
and compiles from it.

**`sync` rebuilds and never merges.** It takes the tree of the upstream commit, keeps what `kept`
names, and writes the result as a commit whose parents are the tip `tint-only` had and the upstream
commit. The second parent keeps every commit ever pinned reachable from a branch that only moves
forward; no content is merged, so nothing the list does not name can arrive.

**`sync` runs every case first, checks the commit it built, and only then moves the branch** — and
only if the branch still names the commit it named when `sync` began. It refuses to run from a tool
or a list that differs from the committed one: a trimmed commit records the revision of this branch
that made it, and that has to be the recipe that was used.

**A trimmed commit that Tint does not configure from is a line missing in `kept`.** Nothing here can
know what a newer Dawn's configure reads. Add the line, commit it on this branch, and `sync` the same
tag again: the new commit goes over the short one, which nothing pins.

The first commit of `tint-only` was not made from a tag, since the commit pinned then had none:

```sh
python3 tint_only.py init --upstream <full commit id>
```

## What `verify` holds

| Rule | What it refuses |
| --- | --- |
| `parents` | anything but one parent for a first trimmed commit, or two for a later one with the upstream commit last |
| `record` | a message whose `Upstream:` is not the last parent, or whose `Recipe:` names no revision of this branch that is here |
| `upstream` | a last parent `dawn.googlesource.com` does not serve |
| `deletions` | a path added, edited or given another mode against the upstream parent |
| `composition` | a path outside the list, or one the list names that is absent |
| `kept` | a kept directory, file or gitlink that is not the object the upstream commit has |

The list a commit is held to is the one at the revision its message records, so an old commit is
checked against the list that made it, and never against where `tint-only` is now.

**It checks that a commit is a correct trim, not that Tint builds from it.**

## Two things to know about the repository it runs in

- **A commit it lacks is fetched at depth 1**, which marks that commit as a shallow boundary. In a
  clone made for this that is what is wanted; a full clone that already has the upstream commit is
  left alone.
- **GitHub's "Sync fork" is not for `tint-only`.** A merge of upstream's `main` into the branch
  would be the whole of Dawn arriving, the one thing `sync` exists to prevent. What the button
  offers on this branch has not been looked at; the branch is moved by a push of what `sync` made
  and by nothing else.
