# `tint-only`: Dawn, trimmed to what Tint's build reads

This is a fork of [Dawn](https://dawn.googlesource.com/dawn) kept for one purpose: building Tint,
Dawn's WGSL compiler, without taking the rest of Dawn. This is not where to get Dawn, and nothing
here is developed; for the project itself see [google/dawn](https://github.com/google/dawn).

| Branch | What it is |
| --- | --- |
| `tint-only`, the default | Dawn with everything Tint's build does not read deleted. Each commit is an upstream commit with paths removed and nothing else |
| `tint-only-tools`, this one | the tool that makes such a commit and checks it, and the list of what is kept |
| `main` | upstream's `main` as it was forked, there so that a trimmed commit has upstream's history to stand on |

Nothing on `tint-only` is authored here. The last parent of each of its commits is the upstream
commit it was made from, so plain git answers where it came from:

```sh
git diff --name-status --no-renames <upstream> <trimmed>     # every line is a D
```

That is why the tool, and this text, live on a branch of their own. The page GitHub shows for the
repository is therefore Dawn's own `README.md`, kept as upstream wrote it; its logo and its links
into `docs/` point at paths that are deleted here.

## Taking it as a submodule

Pin a commit of `tint-only` and fetch at depth 1: the commit is all a build reads.

```sh
git submodule add --depth 1 https://github.com/arcsine-project/dawn external/dawn
git -C external/dawn submodule update --init --depth 1
```

The second line takes the three submodules Tint builds from: abseil, SPIRV-Headers and SPIRV-Tools,
at the commits upstream pins. `.gitmodules` still names all 67 of Dawn's, since it is upstream's
file; three gitlinks are left, and a recursive update takes those three and nothing else.

With every backend off, Dawn's own CMake configures from what is kept and builds the `tint`
executable, target `tint_cmd_tint_cmd`.

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
and writes the result as a commit whose parents are the tip `tint-only` had and the upstream commit.
The second parent keeps every commit ever pinned reachable from a branch that only moves forward; no
content is merged, so nothing the list does not name can arrive.

`sync` runs every case first, checks the commit it built, and only then moves the branch. It moves
the branch only if the branch still names the commit it named when `sync` began. It refuses to run
from a tool or a list that differs from the committed one: a trimmed commit records the revision of
this branch that made it, and that has to be the recipe that was used.

A trimmed commit that Tint does not configure from is a line missing in `kept`. Nothing here can
know what a newer Dawn's configure reads. Add the line, commit it on this branch, and `sync` the
same tag again: the new commit goes over the short one, which nothing pins.

The first commit of `tint-only` was not made from a tag, since the commit pinned then had none:

```sh
python3 tint_only.py init --upstream <full commit id>
```

## The files

| File | What it is |
| --- | --- |
| `kept` | what a trimmed commit keeps of the upstream commit: three directories, eight files, three gitlinks |
| `tint_only.py` | `init`, `sync`, `verify`, `test` |
| `tint_only_cases.py` | the cases that hold each refusal, on repositories built for the purpose |

They need git and Python (written for 3.10, run with 3.11 and 3.12) and nothing else.

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

It checks that a commit is a correct trim, not that Tint builds from it.

## Three things to know about the repository

- `tint-only` has to stay the default branch. A submodule cloned at depth 1 takes the default
  branch's tip before the commit it pins, and `branch` in a consumer's `.gitmodules` does not change
  that. Measured with `main` as the default: 27.7 MB of Dawn's tip fetched for a checkout of 2 296
  files.
- A commit the tool lacks is fetched at depth 1, which marks that commit as a shallow boundary. In a
  clone made for this that is what is wanted; a full clone that already has the upstream commit is
  left alone.
- GitHub's "Sync fork" is for `main`, not for `tint-only`. A merge of upstream's `main` into
  `tint-only` would be the whole of Dawn arriving, the one thing `sync` exists to prevent. What the
  button offers on that branch has not been looked at; the branch moves by a push of what `sync`
  made and by nothing else.
