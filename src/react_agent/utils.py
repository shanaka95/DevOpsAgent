"""Utility & helper functions."""

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from typing import Any, Dict, List

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI


def get_message_text(msg: BaseMessage) -> str:
    """Get the text content of a message."""
    content = msg.content
    if isinstance(content, str):
        return content
    elif isinstance(content, dict):
        return content.get("text", "")
    else:
        txts = [c if isinstance(c, str) else (c.get("text") or "") for c in content]
        return "".join(txts).strip()


def load_chat_model(
    model_name_or_path: str = "anthropic/claude-3-5-sonnet-20240620",
) -> BaseLanguageModel:
    """Load a chat model.

    Args:
        model_name_or_path: Name of the model to load, in the format "provider/model-name"

    Returns:
        A language model ready for chat.
    """
    provider, model_name = model_name_or_path.split("/", 1)

    if provider == "anthropic":
        return ChatAnthropic(model=model_name)
    elif provider == "openai":
        return ChatOpenAI(model=model_name)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


async def summarize_messages(
    messages: List[BaseMessage], 
    model: BaseLanguageModel,
    max_messages_to_keep: int = 4,
    summary_prompt: str = None
) -> List[BaseMessage]:
    """Summarize a list of messages to reduce token usage.
    
    Args:
        messages: List of messages to summarize
        model: Language model to use for summarization
        max_messages_to_keep: Number of most recent messages to keep unchanged
        summary_prompt: Prompt to use for summarization (if None, uses default)
        
    Returns:
        A new list with summarized history and recent messages
    """
    from react_agent.prompts import MEMORY_SUMMARIZATION_PROMPT
    
    # If we don't have enough messages to summarize, return as is
    if len(messages) <= max_messages_to_keep:
        return messages
    
    # Split into messages to summarize and recent messages to keep
    messages_to_summarize = messages[:-max_messages_to_keep]
    recent_messages = messages[-max_messages_to_keep:]
    
    # Create a summary request with the appropriate prompt
    if not summary_prompt:
        summary_prompt = MEMORY_SUMMARIZATION_PROMPT
        
    summary_request = HumanMessage(content=summary_prompt)
    
    # Perform the summarization
    summary_response = await model.ainvoke([*messages_to_summarize, summary_request])
    
    # Replace the history with a summary message
    summary_message = AIMessage(content=f"Conversation history summary: {summary_response.content}")
    
    # Return the summarized state
    return [summary_message] + recent_messages


def extract_tool_related_messages(messages: List[BaseMessage]) -> Dict[str, Any]:
    """Extract tool calls and their responses from messages.
    
    Args:
        messages: List of messages to process
        
    Returns:
        Dictionary with tool usage information
    """
    tools_data = {}
    current_tool_id = None
    
    for msg in messages:
        # Track tool calls
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_id = tool_call.id
                tools_data[tool_id] = {
                    "name": tool_call.name,
                    "args": tool_call.args,
                    "response": None
                }
                current_tool_id = tool_id
        
        # Track tool responses
        elif isinstance(msg, ToolMessage) and current_tool_id:
            if current_tool_id in tools_data:
                tools_data[current_tool_id]["response"] = msg.content
    
    return tools_data
