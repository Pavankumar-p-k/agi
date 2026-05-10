from governance.RuntimeGovernanceLayer import RuntimeGovernanceLayer as GovernanceAlias
from jarvis_os.RuntimeGovernanceLayer import RuntimeGovernanceLayer as GovernanceCanonical


def test_governance_duplicate_collapsed_to_canonical():
    assert GovernanceAlias is GovernanceCanonical
