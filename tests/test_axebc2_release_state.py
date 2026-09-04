import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from axebc2_release_state import APP_DIGEST,APP_TAG,CORE_DIGEST,CORE_TAG,validate
class ReleaseStateTests(unittest.TestCase):
 def test_no_middle_state(self):
  core=f"{CORE_TAG}@{CORE_DIGEST}"; pre=f"{APP_TAG}@sha256:APP_PROMOTED_DIGEST_REQUIRED\n{core}\n{core}"; validate(pre,"prefinalization")
  with self.assertRaises(ValueError): validate(pre.replace(CORE_DIGEST,"sha256:"+"a"*64,1),"prefinalization")
 def test_final_requires_matching_immutable_pins(self):
  core=f"{CORE_TAG}@{CORE_DIGEST}";text=f"{APP_TAG}@{APP_DIGEST}\n{core}\n{core}";validate(text,"finalized")
  with self.assertRaises(ValueError): validate(text.replace(APP_DIGEST,"sha256:"+"a"*64),"finalized")
  with self.assertRaises(ValueError): validate(text.replace(CORE_DIGEST,"sha256:"+"d"*64,1),"finalized")
 def test_lifecycle_matrix_rejects_cross_phase_validation(self):
  core=f"{CORE_TAG}@{CORE_DIGEST}"
  pre=f"{APP_TAG}@sha256:APP_PROMOTED_DIGEST_REQUIRED\n{core}\n{core}"
  final=f"{APP_TAG}@{APP_DIGEST}\n{core}\n{core}"
  validate(pre,"prefinalization"); validate(final,"finalized")
  with self.assertRaises(ValueError): validate(pre,"finalized")
  with self.assertRaises(ValueError): validate(final,"prefinalization")
