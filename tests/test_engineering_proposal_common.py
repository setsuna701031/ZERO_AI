from core.engineering.engineering_proposal_common import canonical_json,fingerprint,stable_proposal_id,contains_forbidden_payload
from pathlib import Path
def test_canonical_stable_and_forbidden_payload():
 assert canonical_json({"b":1,"a":2})=='{"a":2,"b":1}' and fingerprint({"a":1})==fingerprint({"a":1})
 assert stable_proposal_id("p-",{"a":1}).startswith("p-") and contains_forbidden_payload({"patch":"x"})
def test_production_source_static_boundary():
 root=Path(__file__).parents[1];files=list((root/"core"/"engineering").glob("engineering_proposal*.py"))+[root/"cli"/"zero_engineering_proposal.py"]
 source="\n".join(x.read_text(encoding="utf-8") for x in files)
 for forbidden in ("import subprocess","os.system","shell=True","write_text(","write_bytes(",".unlink(",".rename(",".mkdir(","import shutil","import tempfile","import difflib"):
  assert forbidden not in source
