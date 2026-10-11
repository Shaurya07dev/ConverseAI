import operator
import logging
from typing import Annotated, TypedDict, Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
import asyncio

from ai_core.llm import chat_model, strip_reasoning
from ai_core.domain_schemas import domain_manager

logger = logging.getLogger(__name__)

# --- State Schema ---
class ConversationState(TypedDict):
    session_id: str
    domain: str
    turn_count: int
    transcript_history: Annotated[List[str], operator.add]
    speaker_map: Dict[str, str]
    narrative: str
    structured_data: Dict[str, Any]

class ConversationalGraphAgent:
    """
    Stateful conversational agent using LangGraph.
    Addresses limitations of single-pass summarisation by keeping active context.
    """
    def __init__(self):
        self._llm_instance = None
        self.graph = self._build_graph()

    @property
    def _llm(self):
        # Lazy so importing/constructing the agent never needs an API key
        if self._llm_instance is None:
            self._llm_instance = chat_model()
        return self._llm_instance

    def _build_graph(self):
        builder = StateGraph(ConversationState)
        
        # Nodes
        builder.add_node("ingest", self.node_ingest)
        builder.add_node("classify_roles", self.node_classify_roles)
        builder.add_node("extract_structured", self.node_extract_structured)
        builder.add_node("update_narrative", self.node_update_narrative)
        
        # Edges
        builder.add_edge(START, "ingest")
        builder.add_conditional_edges(
            "ingest",
            self.route_after_ingest,
            {
                "classify_roles": "classify_roles",
                "extract_structured": "extract_structured",
                "update_narrative": "update_narrative"
            }
        )
        
        builder.add_edge("classify_roles", "extract_structured")
        builder.add_edge("extract_structured", "update_narrative")
        builder.add_edge("update_narrative", END)
        
        return builder.compile()

    def route_after_ingest(self, state: ConversationState) -> str:
        """Route conditionally based on state parameters."""
        if not state.get("speaker_map") and state.get("turn_count", 0) <= 5:
            return "classify_roles"
        # Run extractor periodically
        if state.get("turn_count", 0) % 5 == 0:
            return "extract_structured"
        return "update_narrative"

    def node_ingest(self, state: ConversationState) -> Dict:
        """Process incoming transcript chunk."""
        # The history reduction happens automatically with operator.add in TypedDict
        # We just increment the turn count here
        return {"turn_count": state.get("turn_count", 0) + 1}

    def node_classify_roles(self, state: ConversationState) -> Dict:
        """Uses first few turns to identify who is the agent vs user."""
        recent_text = "\n".join(state.get("transcript_history", [])[-5:])
        prompt = f"""
        Analyze this initial conversation and map the speaker tags (e.g. SPEAKER_00, SPEAKER_01) 
        to logical roles based on the '{state.get('domain', 'general')}' domain (e.g. Doctor/Patient, Agent/Customer).
        Return ONLY valid JSON format mapping speakers to roles. Example: {{"SPEAKER_00": "Agent", "SPEAKER_01": "Customer"}}
        
        Transcript:
        {recent_text}
        """
        try:
            res = self._llm.invoke([SystemMessage(content="You are a helpful role-classification assistant. Output valid JSON only."), HumanMessage(content=prompt)])
            import json
            import re
            
            # Extract JSON from potential markdown wrapping
            text = strip_reasoning(res.content)
            json_str = re.search(r'\{.*\}', text, re.DOTALL)
            if json_str:
                speaker_map = json.loads(json_str.group())
                return {"speaker_map": speaker_map}
        except Exception as e:
            logger.error(f"Role classification failed: {e}")
        return {"speaker_map": {}}

    def node_extract_structured(self, state: ConversationState) -> Dict:
        """Use Pydantic structured output to safely extract domain values."""
        domain = state.get("domain", "general")
        schema = domain_manager.get_structured_schema(domain)
        
        # Attach structured output constraint
        llm_with_schema = self._llm.with_structured_output(schema)
        
        prompt = f"""
        Extract relevant {domain} details from this conversation history.
        Update missing portions.
        Transcript:
        {chr(10).join(state.get("transcript_history", []))}
        """
        try:
            extracted = llm_with_schema.invoke([HumanMessage(content=prompt)])
            # Merge with existing
            current_data = state.get("structured_data", {})
            new_data = extracted.model_dump(exclude_unset=True, exclude_none=True)
            current_data.update(new_data)
            return {"structured_data": current_data}
        except Exception as e:
            logger.error(f"Structured extraction failed: {e}")
            return {}

    def node_update_narrative(self, state: ConversationState) -> Dict:
        """Incrementally updates the third-person narrative."""
        current_narrative = state.get("narrative", "")
        recent_turns = "\n".join(state.get("transcript_history", [])[-5:])
        
        prompt = f"""
        You are a third-person observer writing a professional summary.
        Existing Narrative:
        {current_narrative if current_narrative else '[No existing narrative]'}
        
        New Dialogue:
        {recent_turns}
        
        Update the narrative incrementally based on the new dialogue. 
        Do not rewrite from scratch unless necessary. Add the new events factually.
        """
        try:
            res = self._llm.invoke([HumanMessage(content=prompt)])
            return {"narrative": strip_reasoning(res.content)}
        except Exception as e:
            logger.error(f"Narrative update failed: {e}")
            return {"narrative": current_narrative}

    async def process_turn(self, state: ConversationState) -> ConversationState:
        """Run the graph asynchronously."""
        final_state = await asyncio.to_thread(self.graph.invoke, state)
        return final_state
