"""Repository consistency: the skills every agent reads, the CLI entry point, the version and changelog, the taxonomy."""
import os, re, subprocess, sys, unittest

from zotero_librarian import __version__, config, setup_check, taxonomy as tx

PY = sys.executable; ZL = os.path.join(config.ROOT, "zl.py")


class Skills(unittest.TestCase):
    def test_claude_copy_matches_the_agents_source(self): self.assertEqual(setup_check.stale_skills(), [])
    def test_frontmatter_has_name_and_description(self): self.assertEqual(setup_check.skill_problems(), [])
    def test_skills_are_agent_neutral(self):
        """A skill runs `zl.py <command>` and says nothing agent-specific (no tool names, no other agent's syntax)."""
        for name in os.listdir(config.SKILLS_SRC):
            with open(os.path.join(config.SKILLS_SRC, name, "SKILL.md"), encoding="utf-8") as f: s = f.read()
            self.assertIn("zl.py " + {"download": "add"}.get(name, name), s, name)
            for word in ("allowed-tools", "WebSearch", "Bash(", "mcp__"): self.assertNotIn(word, s, f"{name}: {word}")


class Cli(unittest.TestCase):
    def run_zl(self, *args): return subprocess.run([PY, ZL, *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
    def test_version(self): self.assertEqual(self.run_zl("--version").stdout.strip(), f"zotero-librarian {__version__}")
    def test_help_lists_every_skill_command(self):
        out = self.run_zl("--help").stdout
        for cmd in ("add", "tidy", "discover", "refs", "setup", "install"): self.assertIn(f"\n  {cmd} ", out, cmd)
    def test_setup_offline_passes(self):
        r = self.run_zl("setup", "--offline"); self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class Version(unittest.TestCase):
    def test_changelog_starts_with_the_current_version(self):
        """The version rule (AGENTS.md): the newest CHANGELOG entry is __version__; tools/check_commits.py checks each commit."""
        with open(os.path.join(config.ROOT, "CHANGELOG.md"), encoding="utf-8") as f: log = f.read()
        self.assertEqual(re.search(r"^- \*\*v([\d.]+)\*\*", log, re.M).group(1), __version__)


class Commits(unittest.TestCase):
    def test_check_commits_rejects_agent_attribution(self):
        """AGENTS.md: no agent attribution in a commit — tools/check_commits.py fails on such a line, author or committer."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_commits", os.path.join(config.ROOT, "tools", "check_commits.py"))
        cc = importlib.util.module_from_spec(spec); spec.loader.exec_module(cc)
        me = "Jane Doe <jane@example.org>\nJane Doe <jane@example.org>"
        self.assertIsNone(cc.attribution("v0.9: add --from-file for a list of links\n", me))
        self.assertIsNone(cc.attribution("Fix\n\nCo-Authored-By: Jane Doe <jane@example.org>\n", me))
        for bad in ("Fix\n\nCo-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>\n",
                    "Fix\n\nClaude-Session: https://claude.ai/code/session_x\n",
                    "Fix\n\n🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"):
            self.assertIsNotNone(cc.attribution(bad, me), bad)
        self.assertIsNotNone(cc.attribution("Fix\n", "Codex <codex@openai.com>\nJane Doe <jane@example.org>"))


class Taxonomy(unittest.TestCase):
    def test_four_collections_with_one_default(self):
        self.assertEqual(len(tx.COLLECTIONS), 4); self.assertEqual(sum(1 for c in tx.COLLECTION_RULES if c.get("default")), 1)
    def test_venues_have_an_abbreviation_and_a_name_or_pattern(self):
        for v in tx.VENUES: self.assertTrue(v.get("abbr") and (v.get("match") or v.get("name")), v)
    def test_read_axis_contains_the_default_status(self): self.assertIn(tx.DEFAULT_STATUS, tx.READ_AXIS)


if __name__ == "__main__": unittest.main()
