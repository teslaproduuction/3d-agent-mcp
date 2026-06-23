"""
Tests for AI agents
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock
from agents.planner_agent import PlannerAgent
from agents.intelligent_postprocessing_agent import IntelligentPostProcessingAgent, ModelAnalysis
from api_clients.llm_client import LLMClient


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client"""
    client = Mock(spec=LLMClient)
    client.complete = AsyncMock(return_value="Test response")
    client.complete_with_json = AsyncMock(return_value=[
        {
            "object": "test_object",
            "prompt": "test prompt",
            "priority": 1
        }
    ])
    return client


@pytest.mark.asyncio
async def test_planner_agent_plan_scene(mock_llm_client):
    """Test scene planning"""
    planner = PlannerAgent(llm_client=mock_llm_client)

    plan = await planner.plan_scene("A desk organizer")

    assert isinstance(plan, list)
    assert len(plan) > 0
    assert 'object' in plan[0]
    assert 'prompt' in plan[0]


@pytest.mark.asyncio
async def test_planner_agent_refine_prompts(mock_llm_client):
    """Test prompt refinement"""
    planner = PlannerAgent(llm_client=mock_llm_client)

    objects = [
        {"object": "pen holder", "prompt": "a pen holder", "priority": 1}
    ]

    refined = await planner.refine_prompts(objects)

    assert isinstance(refined, list)
    assert len(refined) == len(objects)


def test_model_analysis_dataclass():
    """Test ModelAnalysis dataclass"""
    analysis = ModelAnalysis(
        complexity='medium',
        has_internal_cavities=False,
        max_overhang_angle=35.5,
        overhang_area_mm2=120.0,
        contact_area_mm2=450.0,
        is_printable_without_supports=True,
        recommended_orientation=[[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
        recommended_support_strategy='none',
        print_difficulty='easy'
    )

    assert analysis.complexity == 'medium'
    assert analysis.is_printable_without_supports is True
    assert analysis.recommended_support_strategy == 'none'


def test_intelligent_postprocessing_rotation_matrices():
    """Test rotation matrix generation"""
    agent = IntelligentPostProcessingAgent()

    # Test X rotation
    rot_x = agent._rotation_matrix_x(90)
    assert rot_x.shape == (4, 4)

    # Test Y rotation
    rot_y = agent._rotation_matrix_y(90)
    assert rot_y.shape == (4, 4)

    # Test Z rotation
    rot_z = agent._rotation_matrix_z(90)
    assert rot_z.shape == (4, 4)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
