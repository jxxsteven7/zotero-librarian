"""Repository consistency: the skills every agent reads, the CLI entry point, the taxonomy's venues."""
import os, subprocess, sys, unittest

from zotero_librarian import __version__, config, setup_check, taxonomy as tx

PY = sys.executable; ZL = os.path.join(config.ROOT, "zl.py")


class Skills(unittest.TestCase):
    def test_claude_copy_matches_the_agents_source(self): self.assertEqual(setup_check.stale_skills(), [])
    def test_frontmatter_has_name_and_description(self): self.assertEqual(setup_check.skill_problems(), [])
    def test_skills_are_agent_neutral(self):
        """A skill runs `zl.py <command>` and says nothing agent-specific (no tool names, no other agent's syntax)."""
        for name in os.listdir(config.SKILLS_SRC):
            s = open(os.path.join(config.SKILLS_SRC, name, "SKILL.md"), encoding="utf-8").read()
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


class Taxonomy(unittest.TestCase):
    def test_four_collections_with_one_default(self):
        self.assertEqual(len(tx.COLLECTIONS), 4); self.assertEqual(sum(1 for c in tx.COLLECTION_RULES if c.get("default")), 1)
    def test_venues_have_an_abbreviation_and_a_name_or_pattern(self):
        for v in tx.VENUES: self.assertTrue(v.get("abbr") and (v.get("match") or v.get("name")), v)
    def test_read_axis_contains_the_default_status(self): self.assertIn(tx.DEFAULT_STATUS, tx.READ_AXIS)


if __name__ == "__main__": unittest.main()
