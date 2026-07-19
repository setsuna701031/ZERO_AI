from core.engineering.engineering_runtime_adapter_preparation_review_request import build_runtime_adapter_preparation_review_request
from core.engineering.engineering_runtime_adapter_preparation_review_policy import build_default_runtime_adapter_preparation_review_policy
from core.engineering.engineering_runtime_adapter_preparation_review_eligibility import evaluate_runtime_adapter_preparation_review_eligibility
from core.engineering.engineering_runtime_adapter_preparation_review_findings import build_runtime_adapter_preparation_review_findings
from core.engineering.engineering_runtime_adapter_preparation_review import build_runtime_adapter_preparation_review
from core.engineering.engineering_runtime_adapter_preparation_review_handoff import build_runtime_adapter_preparation_review_handoff
from core.engineering.engineering_runtime_adapter_preparation_review_closure import build_runtime_adapter_preparation_review_closure
from tests.runtime_adapter_preparation_fixtures import pipeline2

def review_request(**kw):
 req,pol,elig,desc,prep,clo,adm,h,s=pipeline2(); prep={**prep,**kw.get('preparation_overrides',{})}; clo={**clo,**kw.get('closure_overrides',{})}; desc={**desc,**kw.get('descriptor_overrides',{})}
 return build_runtime_adapter_preparation_review_request(prep,clo,desc,kw.get('review_context',{'purpose':'passive_review'})),prep,clo,desc

def pipeline3(**kw):
 rr,prep,clo,desc=review_request(**kw); pol=build_default_runtime_adapter_preparation_review_policy(); elig=evaluate_runtime_adapter_preparation_review_eligibility(rr,pol); findings=build_runtime_adapter_preparation_review_findings(rr,pol,elig,kw.get('advisory_findings',[])); review=build_runtime_adapter_preparation_review(rr,pol,elig,findings); handoff=build_runtime_adapter_preparation_review_handoff(review,rr); closure=build_runtime_adapter_preparation_review_closure(rr,pol,elig,findings,review,handoff); return rr,pol,elig,findings,review,handoff,closure,prep,clo,desc
