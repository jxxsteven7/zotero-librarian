"""The rule engine and the agent adjudication round trip, on synthetic papers (no library, no network, no model).
    python3 -m unittest discover -s tests -v"""
import contextlib, io, unittest

from zotero_librarian import pipeline, classify, llm, taxonomy as tx
from zotero_librarian.classify import _rx

ABSTRACT = ("We present a vision-language-action policy for dexterous manipulation. Experiments on a real Franka Panda arm with a "
            "Robotiq gripper show that our imitation learning approach trained from human demonstrations outperforms baselines. "
            "We use a diffusion policy with action chunking.")
BODY = ABSTRACT + ("\n\nExperiments. All real-world experiments are conducted on a Franka Panda arm with a 2F-85 gripper. The diffusion "
                   "policy predicts action chunks of 16 steps. We use flow matching as a baseline.\n\nReferences\n[1] Diffusion policy.")
AGENT = dict(kind="agent", model="agent", url="", key="", timeout=1)


class Patterns(unittest.TestCase):
    def test_alternative_is_case_sensitive_only_when_it_has_capitals(self):
        self.assertTrue(_rx(r"\bALOHA\b").search("we use ALOHA")); self.assertFalse(_rx(r"\bALOHA\b").search("we use aloha"))
        self.assertTrue(_rx("bimanual").search("A BIMANUAL system"))
        self.assertTrue(_rx(r"bimanual|\bALOHA\b").search("BIMANUAL")); self.assertFalse(_rx(r"bimanual|\bALOHA\b").search("aloha"))

    def test_every_taxonomy_pattern_compiles(self):
        for tag, r in tx.RULES.items():
            for p in r.get("patterns", []) + r.get("weak", []): _rx(p)
        for c in tx.COLLECTION_RULES:
            for p in c.get("patterns", []) + c.get("title_patterns", []) + c.get("boundary_patterns", []) + c.get("not_in_title", []): _rx(p)

    def test_rules_only_reference_known_tags(self):
        known = set(tx.RULES)
        for c in tx.COLLECTION_RULES:
            self.assertTrue(set(c.get("requires", [])) <= known, c["name"])
        for tag, r in tx.RULES.items():
            for key in ("implies", "suppresses", "requires"):
                self.assertTrue(set(r.get(key, [])) <= known, f"{tag}.{key}")


class Rules(unittest.TestCase):
    def test_manipulation_paper(self):
        sg = classify.suggest("DexVLA: Dexterous Manipulation with Vision-Language-Action Models", ABSTRACT, BODY)
        self.assertEqual(sg["collection"], "Dex-Manipulation")
        for t in ("method:vla", "embod:gripper", "embod:single-arm", "tech:action-chunking", "tech:diffusion", "modality:vision", "modality:language"):
            self.assertIn(t, sg["sure"], t)
        self.assertIn("tech:flow-matching", sg["maybe"])                 # a baseline mention in the body: candidate, not assigned
        self.assertEqual(sg["flags"], [])

    def test_hardware_named_in_related_work_is_a_candidate_not_a_tag(self):
        a = "We introduce a tactile-driven imitation learning system for cable tracing on a Tesollo DG-5F dexterous hand."
        body = a + ("\n\nRelated work. Most prior work uses parallel-jaw grippers [5]; existing approaches with parallel-jaw grippers "
                    "rely on explicit state estimation. Prior parallel-jaw gripper systems close a feedback loop on cable pose.\n\n"
                    "Experiments. The hand pinches the cable between thumb and index finger; a parallel-jaw gripper holds the far end.")
        sg = classify.suggest("Touch2Trace", a, body)
        self.assertIn("embod:dex-hand", sg["sure"]); self.assertNotIn("embod:gripper", sg["sure"]); self.assertIn("embod:gripper", sg["maybe"])

    def test_appendix_after_the_reference_list_is_kept(self):
        """NeurIPS / CoRL layout: References, then Appendix A with the robot setup. The list is cut, the appendix is not."""
        a = "We study viewpoint robustness of flow-based VLA policies using a scene RGB image, language and proprioception."
        refs = "\n".join(f"[{i}] A. Author, B. Author. Some robot learning paper. In Proc. CoRL, 20{20 + i % 6}." for i in range(12))
        method = "\n\nMethod. We regularize the action-flow velocity field with a cross-view consistency loss on action-equivalent view pairs. " * 12
        body = (a + method + "\n\nReferences\n" + refs + "\n\nA\n\nReal-Robot Details\n\nRobot and action space: RealMan RM-75 7-DoF manipulator with a "
                "parallel-jaw gripper at 15 Hz. The RealMan arm executes delta end-effector actions; the parallel-jaw gripper opens at the end.")
        cut = classify.cut_refs(body)
        self.assertNotIn("Some robot learning paper", cut); self.assertIn("RM-75", cut)
        sg = classify.suggest("Cross-View Action Consistency", a, body)
        self.assertIn("embod:single-arm", sg["sure"]); self.assertTrue("embod:gripper" in sg["sure"] or "embod:gripper" in sg["maybe"])

    def test_negated_modality_in_the_abstract_is_not_assigned(self):
        a = ("We learn a policy from a scene RGB image, language and proprioception, without camera labels, extrinsics, depth, "
             "or point-cloud inputs. Experiments on a Franka Panda arm.")
        sg = classify.suggest("Camera-Robust Policies", a, a)
        self.assertIn("modality:vision", sg["sure"]); self.assertNotIn("modality:point-cloud", sg["sure"]); self.assertNotIn("modality:depth", sg["sure"])

    def test_humanoid_paper(self):
        a = ("We propose a whole-body controller for humanoid robots. Reinforcement learning in simulation with sim-to-real transfer "
             "enables robust locomotion and motion tracking on a Unitree G1 humanoid robot.")
        sg = classify.suggest("HumanoidRL: Whole-Body Control for Humanoid Locomotion", a, a)
        self.assertEqual(sg["collection"], "Humanoid"); self.assertEqual(sg["sure"], ["method:rl", "embod:humanoid"])

    def test_status_only_collection(self):
        a = ("We propose a differential evolution variant with an adaptive mutation strategy. Benchmarks on CEC 2017 functions show "
             "that the evolutionary algorithm outperforms particle swarm optimization.")
        sg = classify.suggest("Adaptive Differential Evolution", a, a)
        self.assertEqual(sg["collection"], "Evolution Algorithm"); self.assertEqual(sg["sure"], [])

    def test_default_collection(self):
        a = ("We introduce a technique for visualizing high-dimensional data by giving each datapoint a location in a two-dimensional map. "
             "The technique is a variation of Stochastic Neighbor Embedding.")
        sg = classify.suggest("Visualizing Data using t-SNE", a, a)
        self.assertEqual(sg["collection"], tx.DEFAULT_COLLECTION); self.assertEqual(sg["sure"], [])

    def test_survey_strips_hardware_and_goes_to_survey_home_too(self):
        a = "This survey reviews vision-language-action models for robot manipulation, covering architectures, datasets and benchmarks."
        sg = classify.suggest("A Survey on Vision-Language-Action Models for Robotic Manipulation", a, a)
        self.assertEqual((sg["collection"], sg["also"]), ("Dex-Manipulation", tx.SURVEY_HOME))
        self.assertEqual(sg["sure"], ["type:survey", "method:vla"])

    def test_check_tags_rejects_values_outside_the_vocabulary(self):
        with contextlib.redirect_stdout(io.StringIO()):                     # check_tags prints its warnings
            self.assertEqual(tx.check_tags(["method:vla", "embod:dex-hand", "status:to-read"]), [])
            self.assertEqual(len(tx.check_tags(["method:nope", "bare"])), 2)


class Status(unittest.TestCase):
    def test_tidy_adds_the_default_status_once(self):
        """tidy writes through the Web API, so it must add status:to-read itself (the connector does it for add)."""
        self.assertIn("status:" + tx.DEFAULT_STATUS, pipeline.with_status(["embod:dex-hand"]))
        self.assertEqual(pipeline.with_status(["embod:dex-hand"], have={"status:read", "notion"}), ["embod:dex-hand"])
        self.assertEqual(pipeline.with_status(["status:to-read-first", "method:rl"]).count("status:to-read-first"), 1)


class AgentAdjudication(unittest.TestCase):
    """ZC_LLM=agent: the script asks about the promotable candidates, the agent answers with --confirm."""
    def test_asks_only_about_promotable_candidates(self):
        sg = llm.suggest("DexVLA", ABSTRACT, BODY, cfg=AGENT)
        self.assertTrue(llm.pending(sg)); self.assertEqual(sg["agent_request"][0], ["tech:flow-matching"])
        self.assertIn("ADJUDICATE", sg["agent_request"][1]); self.assertIn("--confirm", sg["agent_request"][1])

    def test_confirm_promotes_and_keeps_the_collection(self):
        sg = llm.suggest("DexVLA", ABSTRACT, BODY, cfg=AGENT, confirm=["tech:flow-matching"])
        self.assertFalse(llm.pending(sg)); self.assertIn("tech:flow-matching", sg["sure"]); self.assertEqual(sg["collection"], "Dex-Manipulation")
        self.assertEqual(sg["llm"]["model"], "agent")

    def test_confirm_none_equals_rules_only(self):
        none = llm.suggest("DexVLA", ABSTRACT, BODY, cfg=AGENT, confirm=[])
        off = llm.suggest("DexVLA", ABSTRACT, BODY, cfg=dict(AGENT, kind="off"))
        self.assertEqual(none["sure"], off["sure"]); self.assertIn("not confirmed by the agent", none["maybe"]["tech:flow-matching"])

    def test_confirm_refuses_tags_it_did_not_ask_about(self):
        with self.assertRaises(RuntimeError): llm.suggest("DexVLA", ABSTRACT, BODY, cfg=AGENT, confirm=["base:pi0"])


if __name__ == "__main__": unittest.main()
