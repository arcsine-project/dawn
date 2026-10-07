# The tool that makes `tint-only`

This is a fork of [Dawn](https://dawn.googlesource.com/dawn) kept for one purpose: building Tint,
Dawn's WGSL compiler, without taking the rest of Dawn. What it offers is on the default branch, and
that branch's `README.md` says how to take it; this branch is how that one is made.

| Branch | What it is |
| --- | --- |
| `tint-only`, the default | Dawn with everything Tint's build does not read deleted. Each commit is an upstream commit with paths removed, and one file of this fork's own, its `README.md` |
| `tint-only-tools`, this one | the tool that makes such a commit and checks it, the list of what is kept, and the text of that `README.md` |
| `main` | upstream's `main`, there so that a trimmed commit has upstream's history to stand on |

One file on `tint-only` is authored here, and nothing upstream wrote is edited. The last parent of
each of its commits is the upstream commit it was made from, so plain git answers where it came
from:

```sh
git diff --name-status --no-renames <upstream> <trimmed>     # `D` on every line but README.md
```

The one line that is not a `D` is accounted for exactly: `README.md` there is the file
`tint-only.README.md` here, at the revision of this branch the trimmed commit records. Dawn's own
`README.md` describes the whole of Dawn, and its logo and its links into `docs/` point at paths that
are deleted, which is why it is the one path replaced. The tool, its cases and the list stay off
`tint-only`.

## A roll

A roll is made when something that builds from this fork needs a fix upstream has, not to keep the
fork current. It is asked for by one of Dawn's release tags, which
[google/dawn](https://github.com/google/dawn/tags) cuts on weekday nights; the commit a tag names is
fetched from `dawn.googlesource.com`.

```sh
python3 tint_only.py sync v20261002.154047    # build the commit, check it, move the local branch
python3 tint_only.py verify                   # check it again, on its own
git push origin tint-only                     # nothing above pushes
```

Then the consumer moves its pin to the new commit, and its own build says whether Tint configures
and compiles from it.

`sync` rebuilds and never merges. It takes the tree of the upstream commit, keeps what `kept` names,
puts this fork's `README.md` in, and writes the result as a commit whose parents are the tip
`tint-only` had and the upstream commit. The second parent keeps every commit ever pinned reachable
from a branch that only moves forward; no content is merged, so nothing the list does not name can
arrive.

`sync` runs every case first, checks the commit it built, and only then moves the branch. It moves
the branch only if the branch still names the commit it named when `sync` began. It refuses to run
from a tool, a list or a text that differs from the committed one: a trimmed commit records the
revision of this branch that made it, and that has to be the recipe that was used.

## When the list or the text changes, and upstream does not

```sh
python3 tint_only.py remake                   # the tip's upstream commit again, as things are now
```

A trimmed commit that Tint does not configure from is a line missing in `kept`. Nothing here can
know what a newer Dawn's configure reads. Add the line, commit it on this branch, and `remake`: the
same upstream commit is trimmed again and goes over the short one, which nothing pins. The same
command carries an edit of `tint-only.README.md` onto `tint-only`. It keeps the tag the tip was
asked for by, and refuses when nothing would change.

The first commit of `tint-only` was not made from a tag, since the commit pinned then had none:

```sh
python3 tint_only.py init --upstream <full commit id>
```

## The files

| File | What it is |
| --- | --- |
| `kept` | what a trimmed commit keeps of the upstream commit (four directories, seven files, three gitlinks), and the one path whose text is ours |
| `tint-only.README.md` | that text: the `README.md` of `tint-only` |
| `tint_only.py` | `init`, `sync`, `remake`, `verify`, `test` |
| `tint_only_cases.py` | the cases that hold each refusal, on repositories built for the purpose |

They need git and Python (written for 3.10, run with 3.11 and 3.12) and nothing else.

## What `verify` holds

| Rule | What it refuses |
| --- | --- |
| `parents` | anything but one parent for a first trimmed commit, or two for a later one with the upstream commit last |
| `record` | a message whose `Upstream:` is not the last parent, or whose `Recipe:` names no revision of this branch that is here with the list and the text |
| `upstream` | a last parent `dawn.googlesource.com` does not serve |
| `deletions` | a path added, edited or given another mode against the upstream parent, `README.md` aside |
| `composition` | a path outside the list, or one the list names that is absent |
| `kept` | a kept directory, file or gitlink that is not the object the upstream commit has |
| `ours` | a `README.md` that is not the text the recorded revision has |

The list and the text a commit is held to are the ones at the revision its message records, so an
old commit is checked against what made it, and never against where `tint-only` is now.

It checks that a commit is a correct trim, not that Tint builds from it.

## Three things to know about the repository

- `tint-only` has to stay the default branch. A submodule cloned at depth 1 takes the default
  branch's tip before the commit it pins, and `branch` in a consumer's `.gitmodules` does not change
  that. Measured both ways: 27.7 MB of Dawn's tip fetched for a checkout of 2 296 files with `main`
  as the default, and 3.8 MB with `tint-only`.
- A commit the tool lacks is fetched at depth 1, which marks that commit as a shallow boundary. In a
  clone made for this that is what is wanted; a full clone that already has the upstream commit is
  left alone.
- GitHub's "Sync fork" is for `main`, not for `tint-only`. A merge of upstream's `main` into
  `tint-only` would be the whole of Dawn arriving, the one thing `sync` exists to prevent. What the
  button offers on that branch has not been looked at; the branch moves by a push of what `sync`
  made and by nothing else.
