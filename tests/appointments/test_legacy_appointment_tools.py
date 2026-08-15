from src.nodes.tools import messages_tools
from src.nodes.tools.services import tools as service_tools


def test_no_legacy_llm_tool_list_exposes_appointment_mutations():
    assert messages_tools == []
    assert service_tools == []
