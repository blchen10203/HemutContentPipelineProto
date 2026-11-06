import pytest
from pydantic import ValidationError

from knowledge.add_feature import NewFeature
from schemas import Claim

VALID_CLAIM = dict(id="voice-agents", type="feature", value="Voice agents", phrasings=["Hemi places check calls"],
                   source_url="https://hemut.com/voice-agents", source_snapshot="knowledge/sources/x.txt",
                   checked="2026-11-06", requires_approval=False)

GOOD = dict(name="Voice agents for check calls", does="Phone agents that place driver check calls",
            url="https://hemut.com/voice-agents", wordings=["Hemi places the driver check calls for you", " ", ""],
            verified_by="Jane Doe (Product Manager)", pain="Dispatchers lose hours chasing drivers for check calls",
            audiences=["dispatcher"])


def nf(**over): return NewFeature(**(GOOD | over))


def test_good_feature_strips_and_drops_blank_wordings():
    f = nf()
    assert f.id == "voice-agents-for-check-calls" and f.wordings == ["Hemi places the driver check calls for you"]


@pytest.mark.parametrize("over, field", [
    ({"url": "http://hemut.com/x"}, "url"), ({"url": "https://hemut.com.evil.io/x"}, "url"),
    ({"url": "https://nothemut.com/x"}, "url"), ({"wordings": ["", " "]}, "wordings"),
    ({"wordings": ["a", "b", "c", "d"]}, "wordings"), ({"verified_by": "Jane Doe"}, "verified_by"),
    ({"pain": "Dispatchers lose 3 hours"}, "pain"), ({"audiences": []}, "audiences"),
    ({"name": "!!!"}, "name"), ({"screenshot": b"x", "screenshot_ext": "png"}, "caption"),
    ({"caption": "Shows the call log"}, "screenshot"),
])
def test_bad_fields_are_rejected(over, field):
    with pytest.raises(ValidationError, match=field):
        nf(**over)


def test_subdomain_url_is_allowed():
    assert nf(url="https://command.hemut.com/x").url == "https://command.hemut.com/x"


def test_claim_takes_verified_by():
    assert Claim.model_validate({**VALID_CLAIM, "verified_by": "Jane Doe (PM)"}).verified_by == "Jane Doe (PM)"
