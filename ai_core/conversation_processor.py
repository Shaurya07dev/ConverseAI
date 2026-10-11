import logging
from ai_core.graph_agent import ConversationalGraphAgent, ConversationState

logger = logging.getLogger(__name__)

class StreamConversationProcessor:
    """
    Handles streaming/incremental conversation chunk processing using the 
    LangGraph Conversational Intelligence Engine.
    """
    def __init__(self):
        self.agent = ConversationalGraphAgent()
        # In-memory per-session state (lost on restart)
        self._session_store = {}

    def get_session_state(self, session_id: str, domain: str = "general") -> ConversationState:
        if session_id not in self._session_store:
            self._session_store[session_id] = ConversationState({
                "session_id": session_id,
                "domain": domain,
                "turn_count": 0,
                "transcript_history": [],
                "speaker_map": {},
                "narrative": "",
                "structured_data": {}
            })
        return self._session_store[session_id]

    async def ingest_chunk(self, session_id: str, domain: str, text_chunk: str) -> dict:
        """
        Takes a new transcript chunk string, runs it through the graph agent, 
        and updates the central state.
        
        Returns a dict of updates for the websocket to push to the client.
        """
        state = self.get_session_state(session_id, domain)
        if not text_chunk.strip():
            logger.warning(f"Empty chunk received for session {session_id}")
            return {"status": "empty"}

        # Push to transcript history (simulated queue)
        state["transcript_history"].append(text_chunk)
        
        # Process the turn through the graph
        logger.info(f"Processing turn for session {session_id} - Graph nodes invoking...")
        try:
            new_state = await self.agent.process_turn(state)
            self._session_store[session_id] = new_state
            
            return {
                "status": "success",
                "narrative": new_state.get("narrative", ""),
                "structured_data": new_state.get("structured_data", {}),
                "speaker_map": new_state.get("speaker_map", {})
            }
        except Exception as e:
            logger.error(f"Graph agent failed on chunk ingestion: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
