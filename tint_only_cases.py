#!/usr/bin/env python3
"""The cases that hold each refusal of `tint_only.py`, and the one acceptance they start from.

    python3 tint_only.py test

**A regression here passes a wrong commit as a trimmed one**, and nothing else would notice: no CI
runs this tool and it is used at intervals of months, which is why `init` and `sync` run every case
before they make anything. Each works on repositories built here, a few files that stand in for
Dawn under the real `kept`, and never on Dawn itself.

Every refusal starts from a pair that passes -- the commit `init` makes of the first upstream
commit and the one `sync` makes of the second -- and changes one thing. A case names the rules that
have to refuse, all of them and no other, so that a commit refused for the wrong reason fails too.
"""

import os
import shutil
import tempfile
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import tint_only
from tint_only import FIRST, Entry, Refused, Repo

WHO = {"GIT_AUTHOR_NAME": "cases", "GIT_AUTHOR_EMAIL": "cases@example.invalid",
       "GIT_COMMITTER_NAME": "cases", "GIT_COMMITTER_EMAIL": "cases@example.invalid",
       "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+0000", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+0000"}
TAG = "v20260101.000000"
SHORT_TAG = "v20260102.000000"

# Gitlinks name commits of other repositories; none of them has to exist here.
LINK_ONE = "1" * 40
LINK_TWO = "2" * 40


def url(path: str) -> str:
    path = path.replace("\\", "/")
    return "file://" + (path if path.startswith("/") else "/" + path)


def new_repo(path: str) -> Repo:
    os.makedirs(path)
    repo = Repo(path)
    repo.git("init", "--quiet")
    # A server answers a request for any commit it has and honours a filter, as upstream's does.
    repo.git("config", "uploadpack.allowAnySHA1InWant", "true")
    repo.git("config", "uploadpack.allowFilter", "true")
    return repo


class Fixture:
    """An upstream of two commits and a tag, and a repository holding the tool's revision in which
    the two trimmed commits are made the way a user makes them."""

    def __init__(self, root: str) -> None:
        with open(os.path.join(tint_only.HERE, tint_only.KEPT), encoding="utf-8") as kept:
            text = kept.read()
        self.recipe = tint_only.parse_recipe(text)
        self.up = new_repo(os.path.join(root, "up"))
        self.work = new_repo(os.path.join(root, "work"))
        self.up_url = url(self.up.path)
        self._identity(self.up)
        self._identity(self.work)

        one, two = (self.up.git("hash-object", "-w", "--stdin", stdin=content)
                    for content in (b"one\n", b"two\n"))
        self.other_blob = self.work.git("hash-object", "-w", "--stdin", stdin=b"not upstream's\n")

        # Everything the list names, and beside it what a trim has to delete: a file, a file under
        # `third_party` the list does not name, and a fourth gitlink.
        first: Dict[str, Entry] = {}
        for tree in self.recipe.trees:
            first[f"{tree}/a.cc"] = Entry("100644", "blob", one, f"{tree}/a.cc")
            first[f"{tree}/sub/b.h"] = Entry("100644", "blob", one, f"{tree}/sub/b.h")
        for path in self.recipe.files:
            first[path] = Entry("100644", "blob", one, path)
        for path in self.recipe.gitlinks:
            first[path] = Entry("160000", "commit", LINK_ONE, path)
        # Upstream has a file of its own wherever this fork writes one, as Dawn has a `README.md`.
        for path, _ in self.recipe.ours:
            first[path] = Entry("100644", "blob", one, path)
        for path in ("test/tint/case.wgsl", "third_party/unnamed.cmake", "tools/run.py"):
            first[path] = Entry("100644", "blob", one, path)
        first["third_party/angle"] = Entry("160000", "commit", LINK_ONE, "third_party/angle")

        # The second upstream commit changes what is kept, as a later Dawn does: a source edited, one
        # added, one removed, a gitlink moved.
        tree = self.recipe.trees[0]
        second = dict(first)
        second[f"{tree}/a.cc"] = Entry("100644", "blob", two, f"{tree}/a.cc")
        second[f"{tree}/new.cc"] = Entry("100644", "blob", two, f"{tree}/new.cc")
        del second[f"{tree}/sub/b.h"]
        link = self.recipe.gitlinks[0]
        second[link] = Entry("160000", "commit", LINK_TWO, link)

        self.u1 = self._commit(self.up, first.values(), [], "upstream, first")
        self.u2 = self._commit(self.up, second.values(), [self.u1], "upstream, second")
        short = [entry for path, entry in second.items() if path != "LICENSE"]
        self.u_short = self._commit(self.up, short, [self.u2], "upstream, without its licence")
        self.up.git("update-ref", "refs/heads/main", self.u_short)
        self.up.git("update-ref", f"refs/tags/{TAG}", self.u2)
        self.up.git("update-ref", f"refs/tags/{SHORT_TAG}", self.u_short)

        # The revision a trimmed commit records: a commit that carries the list and the texts it
        # names. And one that carries the list alone, which a commit cannot be checked against.
        blob = self.work.git("hash-object", "-w", "--stdin", stdin=text.encode("utf-8"))
        tool = [Entry("100644", "blob", blob, tint_only.KEPT)]
        self.bare_revision = self._commit(self.work, tool, [], "the list without its texts")
        for source in self.recipe.sources():
            with open(os.path.join(tint_only.HERE, source), "rb") as written:
                tool.append(Entry("100644", "blob", self.work.git(
                    "hash-object", "-w", "--stdin", stdin=written.read()), source))
        self.revision = self._commit(self.work, tool, [], "the tool")
        self.kept_text = text

        self.t1, _ = tint_only.init(self.work, self.u1, self.revision, self.recipe,
                                    upstream_url=self.up_url)
        self.t2, _ = tint_only.sync(self.work, TAG, self.revision, self.recipe,
                                    upstream_url=self.up_url, tags_url=self.up_url)

        # A commit with the first upstream commit's tree that upstream never made.
        self.foreign = self.work.git("commit-tree", self.work.git("rev-parse", self.u1 + "^{tree}"),
                                     "-m", "not upstream's", env=WHO)

    @staticmethod
    def _identity(repo: Repo) -> None:
        repo.git("config", "user.name", "cases")
        repo.git("config", "user.email", "cases@example.invalid")

    @staticmethod
    def _commit(repo: Repo, entries, parents: Sequence[str], message: str) -> str:
        return tint_only.commit_tree(repo, tint_only.write_tree(repo, entries), parents,
                                     message + "\n", env=WHO)

    def kept(self, upstream: str) -> Dict[str, Entry]:
        """What a correct trim of `upstream` holds, to be changed by a case."""
        return {entry.path: entry for entry in tint_only.recipe_entries(
            self.work, upstream, self.recipe, self.revision)}

    def candidate(self, upstream: str, parents: Sequence[str],
                  change: Optional[Callable[[Dict[str, Entry]], None]] = None,
                  message: Optional[str] = None) -> str:
        entries = self.kept(upstream)
        if change:
            change(entries)
        if message is None:
            message = tint_only.describe(upstream, None, self.revision)
        return self._commit(self.work, entries.values(), parents, message.rstrip("\n"))

    def refused(self, commit: str, expect: Optional[str], rules: Sequence[str],
                prove: bool = False) -> None:
        report = tint_only.verify(self.work, commit, expect=expect, upstream_url=self.up_url,
                                  prove=prove)
        if report.rules() != sorted(rules):
            raise AssertionError(f"refused by {report.rules() or 'nothing'}, and it had to be "
                                 f"{sorted(rules)}: {report.refusals}")

    def passes(self, commit: str, expect: Optional[str], prove: bool = False) -> None:
        self.refused(commit, expect, [], prove)

    def from_upstream(self, upstream: str, path: str) -> Entry:
        return tint_only.listing(self.work, upstream)[path]


def must_refuse(what: Callable[[], object], said: str) -> None:
    try:
        what()
    except Refused as refusal:
        if said not in str(refusal):
            raise AssertionError(f"refused, but not for the reason: {refusal}") from refusal
        return
    raise AssertionError("was not refused")


# --- the pair every refusal starts from ---------------------------------------------------------

def the_first_commit_passes(f: Fixture) -> None:
    f.passes(f.t1, FIRST, prove=True)
    f.passes(f.t1, None)


def a_second_whose_kept_sources_differ_passes(f: Fixture) -> None:
    tree = f.recipe.trees[0]
    first, second = tint_only.listing(f.work, f.t1), tint_only.listing(f.work, f.t2)
    changed = {path for path in set(first) | set(second)
               if path.startswith(tree + "/") and first.get(path) != second.get(path)}
    if len(changed) != 3:
        raise AssertionError(f"the second upstream commit was to change three kept sources: {changed}")
    f.passes(f.t2, f.t1, prove=True)
    f.passes(f.t2, None)
    if tint_only.read_commit(f.work, tint_only.BRANCH).id != f.t2:
        raise AssertionError("the branch does not name the second commit")
    if tint_only.read_commit(f.work, f.t2).trailers("Upstream-tag") != [TAG]:
        raise AssertionError("the second commit does not record the tag it was asked for by")


# --- deletions, composition, kept ---------------------------------------------------------------

def a_kept_file_edited(f: Fixture) -> None:
    def change(entries):
        entries["CMakeLists.txt"] = Entry("100644", "blob", f.other_blob, "CMakeLists.txt")
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["deletions", "kept"])


def a_file_added(f: Fixture) -> None:
    def change(entries):
        entries["tint_only.py"] = Entry("100644", "blob", f.other_blob, "tint_only.py")
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["composition", "deletions"])


def a_mode_changed(f: Fixture) -> None:
    def change(entries):
        entries["LICENSE"] = Entry("100755", "blob", entries["LICENSE"].id, "LICENSE")
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["deletions", "kept"])


def the_licence_removed(f: Fixture) -> None:
    f.refused(f.candidate(f.u1, [f.u1], lambda entries: entries.pop("LICENSE")), FIRST,
              ["composition", "kept"])


def a_kept_cmake_file_removed(f: Fixture) -> None:
    f.refused(f.candidate(f.u1, [f.u1], lambda entries: entries.pop("third_party/CMakeLists.txt")),
              FIRST, ["composition", "kept"])


def a_file_removed_from_a_kept_directory(f: Fixture) -> None:
    path = f.recipe.trees[1] + "/sub/b.h"
    f.refused(f.candidate(f.u1, [f.u1], lambda entries: entries.pop(path)), FIRST, ["kept"])


def a_nested_gitlink_removed(f: Fixture) -> None:
    link = f.recipe.gitlinks[1]
    f.refused(f.candidate(f.u1, [f.u1], lambda entries: entries.pop(link)), FIRST,
              ["composition", "kept"])


def a_nested_gitlink_naming_another_commit(f: Fixture) -> None:
    link = f.recipe.gitlinks[1]

    def change(entries):
        entries[link] = Entry("160000", "commit", LINK_TWO, link)
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["deletions", "kept"])


def a_fourth_gitlink_kept(f: Fixture) -> None:
    def change(entries):
        entries["third_party/angle"] = f.from_upstream(f.u1, "third_party/angle")
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["composition"])


def a_path_outside_the_list_kept(f: Fixture) -> None:
    def change(entries):
        entries["third_party/unnamed.cmake"] = f.from_upstream(f.u1, "third_party/unnamed.cmake")
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["composition"])


# --- the file of this fork's own ----------------------------------------------------------------

def our_file_with_another_text(f: Fixture) -> None:
    path = f.recipe.ours[0][0]

    def change(entries):
        entries[path] = Entry("100644", "blob", f.other_blob, path)
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["ours"])


def upstreams_file_where_ours_belongs(f: Fixture) -> None:
    path = f.recipe.ours[0][0]

    def change(entries):
        entries[path] = f.from_upstream(f.u1, path)
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["ours"])


def our_file_with_another_mode(f: Fixture) -> None:
    path = f.recipe.ours[0][0]

    def change(entries):
        entries[path] = Entry("100755", "blob", entries[path].id, path)
    f.refused(f.candidate(f.u1, [f.u1], change), FIRST, ["ours"])


def our_file_absent(f: Fixture) -> None:
    path = f.recipe.ours[0][0]
    f.refused(f.candidate(f.u1, [f.u1], lambda entries: entries.pop(path)), FIRST, ["composition"])


def a_recipe_without_the_text_it_names(f: Fixture) -> None:
    message = tint_only.describe(f.u1, None, f.bare_revision)
    f.refused(f.candidate(f.u1, [f.u1], message=message), FIRST, ["record"])
    must_refuse(lambda: tint_only.recipe_tree(f.work, f.u1, f.recipe, f.bare_revision), "has no")


# --- parents and the record ---------------------------------------------------------------------

def a_first_commit_with_two_parents(f: Fixture) -> None:
    f.refused(f.candidate(f.u1, [f.revision, f.u1]), FIRST, ["parents"])
    # On its own it is read as a later commit, whose first parent has to be a trimmed one.
    f.refused(f.candidate(f.u1, [f.revision, f.u1]), None, ["parents"])


def a_later_commit_with_one_parent(f: Fixture) -> None:
    f.refused(f.candidate(f.u2, [f.u2]), f.t1, ["parents"])


def the_parents_in_the_other_order(f: Fixture) -> None:
    commit = f.candidate(f.u2, [f.u2, f.t1])
    f.refused(commit, f.t1, ["parents", "record"])
    f.refused(commit, None, ["parents", "record"])


def a_first_parent_that_is_not_the_tip_before(f: Fixture) -> None:
    commit = f.candidate(f.u2, [f.t1, f.u2])
    f.passes(commit, f.t1)
    f.refused(commit, f.revision, ["parents"])
    f.refused(f.candidate(f.u2, [f.u1, f.u2]), None, ["parents"])


def a_third_parent(f: Fixture) -> None:
    commit = f.candidate(f.u2, [f.t1, f.u1, f.u2])
    f.refused(commit, f.t1, ["parents"])
    f.refused(commit, None, ["parents"])


def an_upstream_parent_upstream_does_not_have(f: Fixture) -> None:
    commit = f.candidate(f.foreign, [f.foreign])
    f.passes(commit, FIRST, prove=False)
    f.refused(commit, FIRST, ["upstream"], prove=True)


def a_record_that_names_another_upstream(f: Fixture) -> None:
    message = tint_only.describe(f.u2, None, f.revision)
    f.refused(f.candidate(f.u1, [f.u1], message=message), FIRST, ["record"])


def a_record_without_a_recipe(f: Fixture) -> None:
    message = f"Dawn, trimmed\n\nUpstream: {f.u1}\n"
    f.refused(f.candidate(f.u1, [f.u1], message=message), FIRST, ["record"])
    unknown = tint_only.describe(f.u1, None, "3" * 40)
    f.refused(f.candidate(f.u1, [f.u1], message=unknown), FIRST, ["record"])


def an_old_commit_is_not_held_to_the_branch(f: Fixture) -> None:
    """The first commit checked on its own after the branch has moved past it."""
    if tint_only.read_commit(f.work, tint_only.BRANCH).id == f.t1:
        raise AssertionError("the branch was to have moved on")
    f.passes(f.t1, None)


# --- init, sync and what they refuse before a commit exists -------------------------------------

def init_where_the_branch_exists(f: Fixture) -> None:
    must_refuse(lambda: tint_only.init(f.work, f.u1, f.revision, f.recipe, upstream_url=f.up_url),
                "already exists")


def sync_of_a_tag_nobody_cut(f: Fixture) -> None:
    must_refuse(lambda: tint_only.sync(f.work, "v19990101.000000", f.revision, f.recipe,
                                       upstream_url=f.up_url, tags_url=f.up_url), "has no tag")


def sync_of_an_upstream_that_lacks_what_is_kept(f: Fixture) -> None:
    before = tint_only.read_commit(f.work, tint_only.BRANCH).id
    must_refuse(lambda: tint_only.sync(f.work, SHORT_TAG, f.revision, f.recipe,
                                       upstream_url=f.up_url, tags_url=f.up_url),
                "lacks what kept names: LICENSE")
    if tint_only.read_commit(f.work, tint_only.BRANCH).id != before:
        raise AssertionError("a refused sync moved the branch")


def sync_of_the_tag_the_tip_was_made_from(f: Fixture) -> None:
    must_refuse(lambda: tint_only.sync(f.work, TAG, f.revision, f.recipe,
                                       upstream_url=f.up_url, tags_url=f.up_url), "nothing to make")


def a_commit_that_fails_its_check_moves_nothing(f: Fixture) -> None:
    """Made as `sync` makes one, of a commit upstream does not serve: built, refused, left behind."""
    before = tint_only.read_commit(f.work, tint_only.BRANCH).id
    must_refuse(lambda: tint_only.make(f.work, f.foreign, before, None, f.revision, f.recipe,
                                       f.up_url), "does not pass its own check")
    if tint_only.read_commit(f.work, tint_only.BRANCH).id != before:
        raise AssertionError("a commit that failed its check moved the branch")


def a_branch_that_moved_meanwhile(f: Fixture) -> None:
    other = f.candidate(f.u2, [f.t1, f.u2])
    must_refuse(lambda: tint_only.move_branch(f.work, other, f.t1), "nothing was moved")
    must_refuse(lambda: tint_only.move_branch(f.work, other, tint_only.ZERO), "nothing was moved")
    if tint_only.read_commit(f.work, tint_only.BRANCH).id != f.t2:
        raise AssertionError("a refused move moved the branch")


def a_tool_that_differs_from_the_committed_one(f: Fixture) -> None:
    directory = os.path.join(os.path.dirname(f.work.path), "tool")
    tool = new_repo(directory)
    Fixture._identity(tool)
    must_refuse(lambda: tint_only.tool_revision(directory), "no revision")
    texts = f.recipe.sources()
    for name in (*tint_only.TOOL_FILES, *texts):
        shutil.copyfile(os.path.join(tint_only.HERE, name), os.path.join(directory, name))
    tool.git("add", "--", *tint_only.TOOL_FILES[:-1])
    tool.git("commit", "--quiet", "-m", "without the list", env=WHO)
    must_refuse(lambda: tint_only.tool_revision(directory), f"{tint_only.KEPT} is not committed")
    tool.git("add", "--", tint_only.KEPT)
    tool.git("commit", "--quiet", "-m", "with it, without the text it names", env=WHO)
    must_refuse(lambda: tint_only.tool_revision(directory), f"{texts[0]} is not committed")
    tool.git("add", "--", *texts)
    tool.git("commit", "--quiet", "-m", "with both", env=WHO)
    if tint_only.tool_revision(directory) != tool.git("rev-parse", "HEAD"):
        raise AssertionError("a committed tool did not answer with its commit")
    with open(os.path.join(directory, texts[0]), "a", encoding="utf-8", newline="\n") as written:
        written.write("one more line\n")
    must_refuse(lambda: tint_only.tool_revision(directory), f"{texts[0]} differs")
    tool.git("commit", "--quiet", "-am", "the text, a line longer", env=WHO)
    with open(os.path.join(directory, tint_only.KEPT), "a", encoding="utf-8", newline="\n") as kept:
        kept.write("file     tools/run.py\n")
    must_refuse(lambda: tint_only.tool_revision(directory), f"{tint_only.KEPT} differs")


def a_list_that_is_not_one(f: Fixture) -> None:
    for text, said in (("folder src/tint\n", "expected"), ("file a b\n", "expected"),
                       ("file LICENSE\nfile LICENSE\n", "named twice"),
                       ("tree src/tint/\n", "not a path"), ("file ../LICENSE\n", "not a path"),
                       ("tree src\nfile src/a.cc\n", "kept whole"), ("# nothing\n", "names nothing"),
                       ("ours README.md\n", "expected"), ("ours README.md sub/text.md\n", "beside"),
                       ("file README.md\nours README.md text.md\n", "named twice")):
        must_refuse(lambda text=text: tint_only.parse_recipe(text), said)


def a_tip_that_is_not_a_trimmed_commit_is_not_made_again(f: Fixture) -> None:
    plain = new_repo(os.path.join(os.path.dirname(f.work.path), "plain"))
    commit = Fixture._commit(plain, [Entry("100644", "blob", plain.git(
        "hash-object", "-w", "--stdin", stdin=b"a file\n"), "a.txt")], [], "an ordinary commit")
    must_refuse(lambda: tint_only.remake(plain, f.revision, f.recipe, upstream_url=f.up_url),
                "there is no tint-only")
    plain.git("update-ref", tint_only.BRANCH, commit)
    must_refuse(lambda: tint_only.remake(plain, f.revision, f.recipe, upstream_url=f.up_url),
                "not a trimmed commit")


def the_same_upstream_made_again_by_another_list(f: Fixture) -> None:
    """Last of the cases, since it moves the branch: a line added to the list, upstream as it was."""
    before = tint_only.read_commit(f.work, tint_only.BRANCH)
    must_refuse(lambda: tint_only.remake(f.work, f.revision, f.recipe, upstream_url=f.up_url),
                "nothing to make")

    text = f.kept_text + "file     third_party/unnamed.cmake\n"
    tool = [Entry("100644", "blob", f.work.git("hash-object", "-w", "--stdin", stdin=text.encode()),
                  tint_only.KEPT)]
    tool += [entry for path, entry in tint_only.listing(f.work, f.revision).items()
             if path != tint_only.KEPT]
    longer = Fixture._commit(f.work, tool, [f.revision], "the list, a line longer")
    commit, _ = tint_only.remake(f.work, longer, tint_only.parse_recipe(text), upstream_url=f.up_url)

    made = tint_only.read_commit(f.work, commit)
    if made.parents != (before.id, before.parents[-1]):
        raise AssertionError(f"its parents are {made.parents}, and they were to be the tip before "
                             f"and that tip's upstream")
    if made.trailers("Upstream-tag") != before.trailers("Upstream-tag") or not made.trailers("Upstream-tag"):
        raise AssertionError("the tag the tip was asked for by was not carried over")
    if "third_party/unnamed.cmake" not in tint_only.listing(f.work, commit):
        raise AssertionError("the line added to the list kept nothing")
    if tint_only.read_commit(f.work, tint_only.BRANCH).id != commit:
        raise AssertionError("the branch does not name the commit made again")
    f.passes(commit, before.id, prove=True)
    f.passes(commit, None)
    # And the one before it is still held to the list that made it, a line shorter.
    f.passes(before.id, None)


CASES: Tuple[Callable[[Fixture], None], ...] = (
    the_first_commit_passes,
    a_second_whose_kept_sources_differ_passes,
    a_kept_file_edited,
    a_file_added,
    a_mode_changed,
    the_licence_removed,
    a_kept_cmake_file_removed,
    a_file_removed_from_a_kept_directory,
    a_nested_gitlink_removed,
    a_nested_gitlink_naming_another_commit,
    a_fourth_gitlink_kept,
    a_path_outside_the_list_kept,
    our_file_with_another_text,
    upstreams_file_where_ours_belongs,
    our_file_with_another_mode,
    our_file_absent,
    a_recipe_without_the_text_it_names,
    a_first_commit_with_two_parents,
    a_later_commit_with_one_parent,
    the_parents_in_the_other_order,
    a_first_parent_that_is_not_the_tip_before,
    a_third_parent,
    an_upstream_parent_upstream_does_not_have,
    a_record_that_names_another_upstream,
    a_record_without_a_recipe,
    an_old_commit_is_not_held_to_the_branch,
    init_where_the_branch_exists,
    sync_of_a_tag_nobody_cut,
    sync_of_an_upstream_that_lacks_what_is_kept,
    sync_of_the_tag_the_tip_was_made_from,
    a_commit_that_fails_its_check_moves_nothing,
    a_branch_that_moved_meanwhile,
    a_tool_that_differs_from_the_committed_one,
    a_list_that_is_not_one,
    a_tip_that_is_not_a_trimmed_commit_is_not_made_again,
    the_same_upstream_made_again_by_another_list,
)


def count() -> int:
    return len(CASES)


def run(verbose: bool = False) -> List[str]:
    """Every case, on one fixture. What comes back is each failure in a line; nothing is all held."""
    root = tempfile.mkdtemp(prefix="tint-only-cases-")
    failures: List[str] = []
    try:
        try:
            fixture = Fixture(root)
        except Exception as failure:  # pylint: disable=broad-except
            said = f"the pair every case starts from could not be made: {failure}"
            if verbose:
                print(f"  FAILED  {said}")
            return [said]
        for case in CASES:
            name = case.__name__.replace("_", " ")
            try:
                case(fixture)
                if verbose:
                    print(f"  ok      {name}")
            # Anything a case raises is that case failing, a defect in the tool included.
            except Exception as failure:  # pylint: disable=broad-except
                said = str(failure) or type(failure).__name__
                failures.append(f"{name}: {said}")
                if verbose:
                    print(f"  FAILED  {name}: {said}")
    finally:
        tint_only.remove_tree(root)
    return failures
