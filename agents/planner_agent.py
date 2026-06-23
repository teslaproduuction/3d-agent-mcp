"""
Planner Agent for decomposing user requests into 3D generation tasks
"""
from typing import List, Dict
from api_clients.llm_client import LLMClient


class PlannerAgent:
    """
    Agent for analyzing user requests and creating generation plans
    """

    SYSTEM_PROMPT = """
You are a 3D generation planning expert. Your task is to analyze user requests and break them down into individual 3D objects that need to be generated.

For each object, you need to:
1. Identify the object name
2. Create a detailed 3D generation prompt
3. Assign priority (1 = highest)
4. Specify quantity if multiple copies needed

Guidelines:
- Be specific and descriptive in prompts
- Include materials, style, and important details
- Consider how objects will be 3D printed
- Break complex assemblies into individual parts

Example:
User: "A desk organizer with pen holder and phone stand"

Output:
[
  {
    "object": "desk organizer base",
    "prompt": "rectangular desk organizer base with compartments, minimalist design, white matte finish, suitable for 3D printing",
    "priority": 1
  },
  {
    "object": "pen holder",
    "prompt": "cylindrical pen holder with 5 slots, modern design, integrated mounting for desk organizer",
    "priority": 2
  },
  {
    "object": "phone stand",
    "prompt": "angled phone stand with anti-slip surface, adjustable angle, mounts to desk organizer",
    "priority": 3
  }
]

Always output valid JSON array.
"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def plan_scene(self, user_request: str) -> List[Dict]:
        """
        Decompose user request into individual objects

        Args:
            user_request: User's description of what they want

        Returns:
            List of object specifications
        """
        prompt = f"""
Analyze this request and break it down into individual 3D objects:

Request: "{user_request}"

Return a JSON array of objects with this structure:
[
  {{
    "object": "object name",
    "prompt": "detailed 3D generation prompt",
    "priority": 1,
    "quantity": 1
  }}
]
"""

        result = await self.llm.complete_with_json(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.7
        )

        # Handle both array and object responses
        if isinstance(result, list):
            objects = result
        elif isinstance(result, dict) and 'objects' in result:
            objects = result['objects']
        else:
            # Fallback: treat entire result as single object
            objects = [result]

        # Validate and set defaults
        for obj in objects:
            obj.setdefault('priority', 1)
            obj.setdefault('quantity', 1)
            obj.setdefault('object', 'unknown_object')
            obj.setdefault('prompt', user_request)

            # Ensure prompt is always a string, not a list
            if isinstance(obj['prompt'], list):
                obj['prompt'] = ' '.join(str(item) for item in obj['prompt'])
            elif not isinstance(obj['prompt'], str):
                obj['prompt'] = str(obj['prompt'])

        return objects

    async def refine_prompts(self, objects: List[Dict]) -> List[Dict]:
        """
        Enhance prompts for better 3D generation quality

        Args:
            objects: List of object specifications

        Returns:
            Enhanced object specifications
        """
        refinement_prompt = """
You are a 3D generation expert. Enhance these object prompts for optimal 3D model generation.

Guidelines:
- Add material descriptions (plastic, metal, wood, etc.)
- Specify surface finish (matte, glossy, textured)
- Include style keywords (modern, minimalist, industrial)
- Add lighting hints (studio lit, well-defined edges)
- Ensure prompts are 3D printing friendly

Return enhanced prompts in the same JSON structure.
"""

        objects_json = str(objects)
        prompt = f"""
Enhance these object prompts:

{objects_json}

Return the same JSON structure with improved prompts.
"""

        result = await self.llm.complete_with_json(
            prompt=prompt,
            system_prompt=refinement_prompt,
            temperature=0.5
        )

        # Handle response format
        if isinstance(result, list):
            refined = result
        elif isinstance(result, dict) and 'objects' in result:
            refined = result['objects']
        else:
            # Fallback: return original
            return objects

        # Ensure all required fields are present
        for i, refined_obj in enumerate(refined):
            if i < len(objects):
                # Merge with original to keep all fields
                new_prompt = refined_obj.get('prompt', objects[i]['prompt'])
                if 'enhanced_prompt' in refined_obj:
                    new_prompt = refined_obj['enhanced_prompt']

                # Debug logging
                from utils.logger import get_logger
                logger = get_logger(__name__)
                logger.debug(f"Refine {i}: new_prompt type = {type(new_prompt)}, value = {new_prompt}")

                # Ensure prompt is always a string, not a list
                if isinstance(new_prompt, list):
                    logger.warning(f"Prompt {i} is a list, converting to string")
                    new_prompt = ' '.join(str(item) for item in new_prompt)
                elif not isinstance(new_prompt, str):
                    logger.warning(f"Prompt {i} is {type(new_prompt)}, converting to string")
                    new_prompt = str(new_prompt)

                objects[i]['prompt'] = new_prompt
                logger.debug(f"Final prompt {i}: {objects[i]['prompt']}")

        return objects

    async def validate_plan(self, objects: List[Dict]) -> Dict:
        """
        Validate generation plan for feasibility

        Args:
            objects: List of object specifications

        Returns:
            Validation result with warnings/suggestions
        """
        validation_prompt = """
You are a 3D printing expert. Analyze this generation plan and provide:
1. Overall feasibility (easy/medium/hard)
2. Potential issues or warnings
3. Suggestions for improvement

Return JSON:
{
  "feasibility": "easy/medium/hard",
  "warnings": ["warning1", "warning2"],
  "suggestions": ["suggestion1", "suggestion2"],
  "estimated_print_time_hours": <number>,
  "estimated_material_grams": <number>
}
"""

        objects_summary = "\n".join([
            f"- {obj['object']}: {obj['prompt']}"
            for obj in objects
        ])

        prompt = f"""
Analyze this 3D generation plan:

{objects_summary}

Provide feasibility assessment and recommendations.
"""

        result = await self.llm.complete_with_json(
            prompt=prompt,
            system_prompt=validation_prompt,
            temperature=0.3
        )

        return result

    async def process_user_message(self, message: str, conversation_history: List[Dict]) -> str:
        """
        Process a chat message from the user

        Args:
            message: User's message
            conversation_history: Previous conversation

        Returns:
            Agent's response
        """
        # Build context from conversation history
        context_lines = []
        for msg in conversation_history[-5:]:  # Last 5 messages
            content = msg['content']
            # Handle different content formats (string or list)
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    if isinstance(item, dict) and 'text' in item:
                        text_parts.append(item['text'])
                    elif isinstance(item, str):
                        text_parts.append(item)
                    else:
                        text_parts.append(str(item))
                content = ' '.join(text_parts)
            elif not isinstance(content, str):
                content = str(content)
            context_lines.append(f"{msg['role']}: {content}")

        context = "\n".join(context_lines)

        prompt = f"""
Previous conversation:
{context}

User: {message}

Respond as a helpful 3D generation planning assistant. Help the user refine their request, ask clarifying questions if needed, or confirm that you understand what they want to generate.
"""

        response = await self.llm.complete(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            temperature=0.8,
            max_tokens=500
        )

        return response

    def __repr__(self):
        return f"PlannerAgent(llm={self.llm})"
