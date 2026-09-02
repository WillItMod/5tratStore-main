import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from axebc2_release_state import APP_TAG,CORE_TAG,validate
class ReleaseStateTests(unittest.TestCase):
 def test_no_middle_state(self):
  pre=f"{APP_TAG}@sha256:APP_PROMOTED_DIGEST_REQUIRED\n{CORE_TAG}@sha256:CORE31_PROMOTED_DIGEST_REQUIRED\n{CORE_TAG}@sha256:CORE31_PROMOTED_DIGEST_REQUIRED"; validate(pre,"prefinalization")
  with self.assertRaises(ValueError): validate(pre.replace("CORE31_PROMOTED_DIGEST_REQUIRED","a"*64,1),"prefinalization")
 def test_final_requires_matching_immutable_pins(self):
  a="sha256:"+"a"*64;c="sha256:"+"c"*64;text=f"{APP_TAG}@{a}\n{CORE_TAG}@{c}\n{CORE_TAG}@{c}";validate(text,"finalized")
  with self.assertRaises(ValueError): validate(text.replace(c,"sha256:"+"d"*64,1),"finalized")
