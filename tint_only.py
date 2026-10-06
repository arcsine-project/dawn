#!/usr/bin/env python3
"""Make and check `tint-only`: Dawn with everything Tint's build does not read deleted.

    python3 tint_only.py init --upstream <sha>    # the first trimmed commit, once
    python3 tint_only.py sync <tag>               # a later one, from one of Dawn's release tags
    python3 tint_only.py verify [<commit>]        # check a trimmed commit; `tint-only` by default
    python3 tint_only.py test                     # the cases that hold each refusal

**A trimmed commit is the upstream commit with paths removed, and nothing else.** Its last parent is
that upstream commit, so plain git answers where it came from with no tool of ours:
`git diff --name-status --no-renames <upstream> <trimmed>` prints nothing but `D`. That is why this
file lives on a branch of its own and not on `tint-only`: nothing authored is in a trimmed commit.

**`sync` rebuilds and never merges.** It takes the tree of the commit the tag names, keeps what
`kept` lists, and writes that as a commit whose parents are the tip `tint-only` had and the upstream
commit. The second parent is there so that every commit ever pinned stays reachable from a branch
that only moves forward; no content is merged, so nothing `kept` does not name can arrive.

**What is checked is that a commit is a correct trim, not that Tint builds from it.** A list one
file short shows when Tint is configured and nowhere earlier; the answer is a line in `kept`, a
commit of this branch, and `sync` again over the same upstream commit.

`init` and `sync` run the cases first, build the commit, check it by the rules `verify` holds, and
only then move the local branch -- and only if it still names the commit it named when they began.
They refuse to run from a tool or a list that differs from the committed one, since the revision a
trimmed commit records has to be the recipe that made it.
"""

import argparse
import dataclasses
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

UPSTREAM = "https://dawn.googlesource.com/dawn"
# Dawn's release tags are cut on its GitHub mirror alone; the commits they name are upstream's.
TAGS = "https://github.com/google/dawn"

BRANCH = "refs/heads/tint-only"
KEPT = "kept"
TOOL_FILES = ("tint_only.py", "tint_only_cases.py", KEPT)
HERE = os.path.dirname(os.path.abspath(__file__))

ZERO = "0" * 40
SHA = re.compile(r"^[0-9a-f]{40}$")
TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# What `verify` is told to expect of a commit's parents: a first trimmed commit, or nothing -- a
# commit checked on its own, long after the branch has moved on. A later one is told the commit id.
FIRST = "first"


class Refused(Exception):
    """A rule said no. The message is what the user reads."""


class GitFailed(Exception):
    """Git answered something this file did not expect; a defect or an environment, not a rule."""


class Repo:
    """A repository, by any path inside it. Bytes in and out, so that a line ends in a line feed
    alone -- in text mode Windows adds a carriage return, and `update-index` then ignores a path."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._listings: Dict[Tuple[str, Tuple[str, ...]], Dict[str, "Entry"]] = {}

    def run(self, *arguments: str, stdin: Optional[bytes] = None,
            env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", self.path, *arguments], input=stdin,
                              capture_output=True, env=dict(os.environ, **(env or {})), check=False)

    def raw(self, *arguments: str, stdin: Optional[bytes] = None,
            env: Optional[Dict[str, str]] = None) -> bytes:
        done = self.run(*arguments, stdin=stdin, env=env)
        if done.returncode != 0:
            said = done.stderr.decode("utf-8", "replace").strip()
            raise GitFailed(f"git {' '.join(arguments[:3])} exited {done.returncode}: {said[-800:]}")
        return done.stdout

    def git(self, *arguments: str, stdin: Optional[bytes] = None,
            env: Optional[Dict[str, str]] = None) -> str:
        return self.raw(*arguments, stdin=stdin, env=env).decode("utf-8", "replace").strip()

    def has(self, name: str) -> bool:
        return self.run("cat-file", "-e", name).returncode == 0


@dataclasses.dataclass(frozen=True)
class Entry:
    mode: str
    kind: str
    id: str
    path: str

    def what(self) -> Tuple[str, str, str]:
        return (self.mode, self.kind, self.id)


@dataclasses.dataclass(frozen=True)
class Recipe:
    """What `kept` names. A gitlink is kept by its own name alone, never for being under a tree."""
    trees: Tuple[str, ...]
    files: Tuple[str, ...]
    gitlinks: Tuple[str, ...]

    def allows(self, entry: Entry) -> bool:
        if entry.kind == "commit":
            return entry.path in self.gitlinks
        return entry.path in self.files or entry.path.startswith(tuple(t + "/" for t in self.trees))

    def named(self) -> List[str]:
        return [*self.trees, *self.files, *self.gitlinks]

    def absent(self, entries: Iterable[Entry]) -> List[str]:
        """Every named path `entries` does not have, a tree counting as there by one file in it."""
        paths = {entry.path: entry for entry in entries}
        absent = [path for path in self.files if path not in paths or paths[path].kind != "blob"]
        absent += [path for path in self.gitlinks
                   if path not in paths or paths[path].kind != "commit"]
        absent += [tree for tree in self.trees
                   if not any(path.startswith(tree + "/") for path in paths)]
        return sorted(absent)


def parse_recipe(text: str) -> Recipe:
    named: Dict[str, List[str]] = {"tree": [], "file": [], "gitlink": []}
    seen = set()
    for number, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or parts[0] not in named:
            raise Refused(f"{KEPT}, line {number}: expected `tree`, `file` or `gitlink` and one path")
        kind, path = parts
        if path.startswith("/") or path.endswith("/") or ".." in path.split("/") or "\\" in path:
            raise Refused(f"{KEPT}, line {number}: {path} is not a path inside the repository")
        if path in seen:
            raise Refused(f"{KEPT}, line {number}: {path} is named twice")
        seen.add(path)
        named[kind].append(path)
    for tree in named["tree"]:
        inside = [path for path in seen if path.startswith(tree + "/")]
        if inside:
            raise Refused(f"{KEPT}: {inside[0]} is inside the tree {tree}, which is kept whole")
    if not seen:
        raise Refused(f"{KEPT} names nothing")
    return Recipe(tuple(named["tree"]), tuple(named["file"]), tuple(named["gitlink"]))


def listing(repo: Repo, commit: str, paths: Sequence[str] = ()) -> Dict[str, Entry]:
    """Every entry under `commit`, or with `paths` the one entry each of them names.

    Remembered per commit id, which names the same tree for good; the upstream commit's 85 000
    entries are read once however many rules ask.
    """
    key = (commit, tuple(paths))
    if key not in repo._listings:
        arguments = ["ls-tree", "-z"] + ([] if paths else ["-r"]) + [commit]
        out = repo.raw(*arguments, *(["--", *paths] if paths else []))
        entries = {}
        for record in out.split(b"\0"):
            if record:
                meta, path = record.split(b"\t", 1)
                mode, kind, name = meta.decode().split()
                text = path.decode("utf-8", "surrogateescape")
                entries[text] = Entry(mode, kind, name, text)
        repo._listings[key] = entries
    return repo._listings[key]


def write_tree(repo: Repo, entries: Iterable[Entry]) -> str:
    """The tree of `entries`, written through an index of its own; no checkout is touched."""
    handle, index = tempfile.mkstemp(prefix="tint-only-", suffix=".index")
    os.close(handle)
    os.unlink(index)
    try:
        data = b"".join(f"{entry.mode} {entry.kind} {entry.id}\t".encode()
                        + entry.path.encode("utf-8", "surrogateescape") + b"\0" for entry in entries)
        environment = {"GIT_INDEX_FILE": index}
        repo.raw("update-index", "-z", "--index-info", stdin=data, env=environment)
        return repo.git("write-tree", env=environment)
    finally:
        for left in (index, index + ".lock"):
            if os.path.exists(left):
                os.unlink(left)


def recipe_tree(repo: Repo, upstream: str, recipe: Recipe) -> str:
    """The tree the list makes of `upstream`; refused when upstream lacks anything it names."""
    kept = [entry for entry in listing(repo, upstream).values() if recipe.allows(entry)]
    absent = recipe.absent(kept)
    if absent:
        raise Refused(f"upstream {upstream[:12]} lacks what {KEPT} names: {', '.join(absent)}")
    return write_tree(repo, kept)


@dataclasses.dataclass(frozen=True)
class Commit:
    id: str
    tree: str
    parents: Tuple[str, ...]
    message: str

    def trailers(self, name: str) -> List[str]:
        return [line.split(":", 1)[1].strip() for line in self.message.splitlines()
                if line.startswith(name + ":")]


def read_commit(repo: Repo, name: str) -> Optional[Commit]:
    """The commit object as it is stored. Its `parent` lines are read from the object, since a
    shallow repository hides the parents of the commit it is cut at from everything that walks."""
    found = repo.run("rev-parse", "--verify", "--quiet", name + "^{commit}")
    if found.returncode != 0:
        return None
    commit = found.stdout.decode().strip()
    headers, _, message = repo.git("cat-file", "commit", commit).partition("\n\n")
    tree = ""
    parents = []
    for line in headers.splitlines():
        if line.startswith("tree "):
            tree = line.split()[1]
        elif line.startswith("parent "):
            parents.append(line.split()[1])
    return Commit(commit, tree, tuple(parents), message)


def describe(upstream: str, tag: Optional[str], revision: str) -> str:
    """A trimmed commit's message. The three lines at its end are its record, and `verify` reads
    them: which upstream commit it claims, by which tag it was asked for, and which revision of this
    tool and its list made it."""
    lines = [f"Dawn at {tag or upstream[:12]}, with what Tint's build does not read deleted", "",
             f"Upstream: {upstream}"]
    if tag:
        lines.append(f"Upstream-tag: {tag}")
    lines.append(f"Recipe: {revision}")
    return "\n".join(lines) + "\n"


def commit_tree(repo: Repo, tree: str, parents: Sequence[str], message: str,
                env: Optional[Dict[str, str]] = None) -> str:
    arguments = ["commit-tree", tree]
    for parent in parents:
        arguments += ["-p", parent]
    return repo.git(*arguments, stdin=message.encode(), env=env)


def remove_tree(path: str) -> None:
    def writable(function, name, _):
        os.chmod(name, stat.S_IWRITE)
        function(name)
    shutil.rmtree(path, onerror=writable)


def upstream_serves(commit: str, url: str) -> bool:
    """Whether `url` has `commit`, asked with a fetch of the commit object alone into a store that is
    thrown away. Measured against `dawn.googlesource.com`: 1.5 KiB and under a second for a commit
    it has, a refusal for one it has not. A server that ignores the filter sends more and answers
    the same."""
    store = tempfile.mkdtemp(prefix="tint-only-proof-")
    try:
        subprocess.run(["git", "init", "--quiet", "--bare", store], check=True, capture_output=True)
        done = subprocess.run(["git", "-C", store, "fetch", "--quiet", "--no-tags", "--depth", "1",
                               "--filter=tree:0", url, commit], capture_output=True, check=False)
        return done.returncode == 0
    finally:
        remove_tree(store)


def obtain(repo: Repo, commit: str, url: str) -> None:
    """Have `commit` and its tree here, fetching it at depth 1 when they are not.

    A depth-1 fetch marks the commit as a shallow boundary in this repository. That is what a clone
    made for this purpose wants and what a full clone of Dawn may not; one that already has the
    commit is left alone.
    """
    if repo.has(commit + "^{tree}"):
        return
    done = repo.run("fetch", "--quiet", "--no-tags", "--depth", "1", url, commit)
    if done.returncode != 0 or not repo.has(commit + "^{tree}"):
        raise Refused(f"{url} did not serve {commit}")


def resolve_tag(tag: str, url: str) -> str:
    if not TAG.match(tag):
        raise Refused(f"{tag!r} is not a tag name")
    done = subprocess.run(["git", "ls-remote", url, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}"],
                          capture_output=True, check=False)
    if done.returncode != 0:
        raise Refused(f"{url} did not answer: {done.stderr.decode('utf-8', 'replace').strip()[-300:]}")
    found = dict(reversed(line.split("\t")) for line in done.stdout.decode().splitlines() if line)
    commit = found.get(f"refs/tags/{tag}^{{}}") or found.get(f"refs/tags/{tag}")
    if not commit:
        raise Refused(f"{url} has no tag {tag}")
    return commit


@dataclasses.dataclass
class Report:
    commit: str
    refusals: List[Tuple[str, str]] = dataclasses.field(default_factory=list)
    passed: List[Tuple[str, str]] = dataclasses.field(default_factory=list)
    notes: List[str] = dataclasses.field(default_factory=list)

    def refuse(self, rule: str, why: str) -> None:
        self.refusals.append((rule, why))

    def rules(self) -> List[str]:
        return sorted({rule for rule, _ in self.refusals})

    def lines(self) -> List[str]:
        lines = [self.commit]
        lines += [f"  {rule:12} ok       {what}" for rule, what in self.passed]
        lines += [f"  {rule:12} REFUSED  {why}" for rule, why in self.refusals]
        lines += [f"  note: {note}" for note in self.notes]
        return lines


def some(paths: Sequence[str]) -> str:
    shown = ", ".join(paths[:5])
    return shown if len(paths) <= 5 else f"{shown} and {len(paths) - 5} more"


def verify(repo: Repo, name: str, expect: Optional[str] = None, upstream_url: str = UPSTREAM,
           prove: bool = True) -> Report:
    """Whether `name` is a correct trimmed commit. Six rules, each reported by its own name.

    `expect` is what the caller knows of the parents: `FIRST` for the commit `init` made, the tip the
    branch had for one `sync` made, and nothing for a commit checked on its own -- which is never
    compared with where the branch is now, since an old pin is no less correct for a newer one.
    """
    commit = read_commit(repo, name)
    if commit is None:
        raise Refused(f"{name} names no commit in this repository")
    report = Report(commit.id)

    # parents: the form asked, the upstream commit always last.
    parents = commit.parents
    if expect == FIRST:
        if len(parents) != 1:
            report.refuse("parents", f"a first trimmed commit has one parent, and this has {len(parents)}")
    elif expect is not None:
        if len(parents) != 2:
            report.refuse("parents", f"a later trimmed commit has two parents, and this has {len(parents)}")
        elif parents[0] != expect:
            report.refuse("parents", f"its first parent is {parents[0][:12]} and the branch's tip was "
                                     f"{expect[:12]}")
    elif len(parents) not in (1, 2):
        report.refuse("parents", f"a trimmed commit has one parent or two, and this has {len(parents)}")
    elif len(parents) == 2:
        before = read_commit(repo, parents[0])
        if before is None:
            report.notes.append(f"its first parent {parents[0][:12]} is not in this repository, so "
                                f"that it is a trimmed commit was not checked")
        elif not before.parents or before.trailers("Upstream") != [before.parents[-1]]:
            report.refuse("parents", f"its first parent {parents[0][:12]} is not a trimmed commit")
    if "parents" not in report.rules():
        report.passed.append(("parents", ", ".join(parent[:12] for parent in parents)))

    # record: what the message claims, which has to be what the commit is.
    claimed = commit.trailers("Upstream")
    revisions = commit.trailers("Recipe")
    recipe = None
    if not parents or claimed != [parents[-1]]:
        report.refuse("record", f"its message names upstream {claimed or 'nothing'}, and its last "
                                f"parent is {parents[-1][:12] if parents else 'absent'}")
    if len(revisions) != 1 or not SHA.match(revisions[0]):
        report.refuse("record", "its message names no one revision of the recipe")
    else:
        found = repo.run("cat-file", "blob", f"{revisions[0]}:{KEPT}")
        if found.returncode != 0:
            report.refuse("record", f"the recipe's revision {revisions[0][:12]} is not in this "
                                    f"repository: fetch the branch this tool lives on")
        else:
            recipe = parse_recipe(found.stdout.decode("utf-8"))
    if "record" not in report.rules():
        tags = commit.trailers("Upstream-tag")
        report.passed.append(("record", f"upstream {claimed[0][:12]}"
                              + (f", asked for as {tags[0]}" if tags else "")
                              + f", recipe {revisions[0][:12]}"))

    # Without an upstream commit that can be trusted and a list, nothing below means anything.
    if report.refusals or recipe is None:
        return report
    upstream = parents[-1]

    # upstream: the last parent is a commit upstream itself serves.
    if prove:
        if upstream_serves(upstream, upstream_url):
            report.passed.append(("upstream", f"{upstream_url} serves {upstream[:12]}"))
        else:
            report.refuse("upstream", f"{upstream_url} does not serve {upstream[:12]}")
    obtain(repo, upstream, upstream_url)

    theirs = listing(repo, upstream)
    ours = listing(repo, commit.id)

    # deletions: against the upstream parent every difference is a deletion.
    added = sorted(path for path in ours if path not in theirs)
    changed = sorted(path for path, entry in ours.items()
                     if path in theirs and theirs[path].what() != entry.what())
    if added:
        report.refuse("deletions", f"added: {some(added)}")
    if changed:
        report.refuse("deletions", f"changed: {some(changed)}")
    if not added and not changed:
        report.passed.append(("deletions", f"{len(theirs) - len(ours)} of upstream's {len(theirs)} "
                                           f"paths deleted, none added or changed"))

    # composition: nothing outside the list, and everything it names.
    outside = sorted(path for path, entry in ours.items() if not recipe.allows(entry))
    absent = recipe.absent(ours.values())
    if outside:
        report.refuse("composition", f"outside the list: {some(outside)}")
    if absent:
        report.refuse("composition", f"named and absent: {some(absent)}")
    if not outside and not absent:
        report.passed.append(("composition", f"{len(ours)} paths, all in the list; all "
                                             f"{len(recipe.named())} it names are there"))

    # kept: each thing the list names is the object upstream has, mode and all.
    named = recipe.named()
    here = listing(repo, commit.id, named)
    there = listing(repo, upstream, named)
    differ = [path for path in named
              if path not in here or path not in there or here[path].what() != there[path].what()]
    if differ:
        report.refuse("kept", f"not upstream's: {some(differ)}")
    else:
        report.passed.append(("kept", f"{len(recipe.trees)} trees, {len(recipe.files)} files and "
                                      f"{len(recipe.gitlinks)} gitlinks are upstream's objects"))

    # And the three together are one comparison, made a second way: a disagreement between the two
    # is a defect in this file, and is reported rather than passed over.
    if not report.refusals and recipe_tree(repo, upstream, recipe) != commit.tree:
        report.refuse("tree", "its tree is not the one the list makes of its upstream parent, and "
                              "no rule above said why")
    return report


def tool_revision(directory: str = HERE) -> str:
    """The commit this tool and its list are at, refused unless both are exactly the committed ones.

    A trimmed commit records this as its recipe; were a changed file allowed to run, the revision
    would name a recipe other than the one used.
    """
    tool = Repo(directory)
    if tool.run("rev-parse", "--verify", "--quiet", "HEAD^{commit}").returncode != 0:
        raise Refused("this tool is not in a repository with a commit, so it has no revision")
    prefix = tool.git("rev-parse", "--show-prefix")
    for name in TOOL_FILES:
        committed = tool.run("rev-parse", "--verify", "--quiet", f"HEAD:{prefix}{name}")
        if committed.returncode != 0:
            raise Refused(f"{name} is not committed on the branch checked out here")
        if tool.git("hash-object", "--", os.path.join(directory, name)) != committed.stdout.decode().strip():
            raise Refused(f"{name} differs from the committed one: commit it, or put it back")
    return tool.git("rev-parse", "HEAD")


def move_branch(repo: Repo, new: str, old: str) -> None:
    """Point `tint-only` at `new`, and only if it still names `old` -- all zeros for "no branch".
    Two runs at once would otherwise both build on the same tip and one would be lost."""
    if repo.run("update-ref", BRANCH, new, old).returncode != 0:
        was = "did not exist" if old == ZERO else f"named {old[:12]}"
        raise Refused(f"tint-only {was} when this began and does not now; nothing was moved")


def run_cases() -> None:
    import tint_only_cases
    failures = tint_only_cases.run()
    if failures:
        raise Refused("the tool's own cases do not hold, so it is not trusted to make a commit:\n  "
                      + "\n  ".join(failures))


def make(repo: Repo, upstream: str, previous: Optional[str], tag: Optional[str], revision: str,
         recipe: Recipe, upstream_url: str, prove: bool = True) -> Tuple[str, Report]:
    """Build the trimmed commit of `upstream`, check it, and move the branch from `previous` to it."""
    obtain(repo, upstream, upstream_url)
    tree = recipe_tree(repo, upstream, recipe)
    if previous is not None:
        before = read_commit(repo, previous)
        if before is not None and before.tree == tree:
            raise Refused(f"the tip of tint-only already has this tree; there is nothing to make")
    parents = [upstream] if previous is None else [previous, upstream]
    commit = commit_tree(repo, tree, parents, describe(upstream, tag, revision))
    report = verify(repo, commit, expect=FIRST if previous is None else previous,
                    upstream_url=upstream_url, prove=prove)
    if report.refusals:
        raise Refused("the commit this made does not pass its own check, and the branch was not "
                      "moved:\n" + "\n".join(report.lines()))
    move_branch(repo, commit, ZERO if previous is None else previous)
    return commit, report


def init(repo: Repo, upstream: str, revision: str, recipe: Recipe, upstream_url: str = UPSTREAM,
         prove: bool = True) -> Tuple[str, Report]:
    if not SHA.match(upstream):
        raise Refused(f"{upstream!r} is not a full commit id")
    if read_commit(repo, BRANCH) is not None:
        raise Refused("tint-only already exists; a later trimmed commit is made by `sync`")
    return make(repo, upstream, None, None, revision, recipe, upstream_url, prove)


def sync(repo: Repo, tag: str, revision: str, recipe: Recipe, upstream_url: str = UPSTREAM,
         tags_url: str = TAGS, prove: bool = True) -> Tuple[str, Report]:
    # Read once, here: this is the commit the new one is built on and the one the branch has to
    # name still when it is moved.
    previous = read_commit(repo, BRANCH)
    if previous is None:
        raise Refused("there is no tint-only here: fetch it, or make the first commit with `init`")
    upstream = resolve_tag(tag, tags_url)
    return make(repo, upstream, previous.id, tag, revision, recipe, upstream_url, prove)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="tint_only", description="Make and check the tint-only branch of this fork of Dawn.")
    commands = parser.add_subparsers(dest="command", required=True)
    first = commands.add_parser("init", help="make the first trimmed commit, from an upstream commit")
    first.add_argument("--upstream", required=True, metavar="SHA", help="the upstream commit, in full")
    later = commands.add_parser("sync", help="make the next trimmed commit, from a release tag")
    later.add_argument("tag", help="one of Dawn's release tags, such as v20261002.154047")
    check = commands.add_parser("verify", help="check a trimmed commit on its own")
    check.add_argument("commit", nargs="?", default=BRANCH, help="default: tint-only")
    commands.add_parser("test", help="run the cases that hold each refusal")
    arguments = parser.parse_args()

    repo = Repo(HERE)
    try:
        if arguments.command == "test":
            import tint_only_cases
            failures = tint_only_cases.run(verbose=True)
            print(f"{len(failures)} of {tint_only_cases.count()} cases failed" if failures
                  else f"all {tint_only_cases.count()} cases hold")
            return 1 if failures else 0

        if arguments.command == "verify":
            report = verify(repo, arguments.commit)
            print("\n".join(report.lines()))
            print("REFUSED" if report.refusals else "verified")
            return 1 if report.refusals else 0

        revision = tool_revision()
        with open(os.path.join(HERE, KEPT), encoding="utf-8") as kept:
            recipe = parse_recipe(kept.read())
        run_cases()
        if arguments.command == "init":
            commit, report = init(repo, arguments.upstream, revision, recipe)
        else:
            commit, report = sync(repo, arguments.tag, revision, recipe)
        print("\n".join(report.lines()))
        print(f"tint-only now names {commit}; nothing was pushed.")
        return 0
    except Refused as refusal:
        print(f"tint_only: {refusal}", file=sys.stderr)
        return 1
    except GitFailed as failure:
        print(f"tint_only: {failure}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
