import streamlit as st
from workflow import initialize_workflow
from langgraph.types import Command
import uuid
import sys
from io import StringIO
import contextlib
import time
from typing import Dict, Any
import threading
import queue

# Custom logging class to capture prints
class StreamlitLogger:
    def __init__(self):
        self.logs = []
        self.output_queue = queue.Queue()
    
    def write(self, message):
        if message.strip():
            self.logs.append(message)
            self.output_queue.put(message)
    
    def flush(self):
        pass

# Initialize session state
if 'workflow' not in st.session_state:
    st.session_state.workflow = initialize_workflow()
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.workflow_config = {
        "configurable": {"thread_id": st.session_state.thread_id},
        "recursion_limit": 500
    }
    st.session_state.logger = StreamlitLogger()
    st.session_state.active_agent = "router"
    st.session_state.agent_outputs = {}
    st.session_state.workflow_completed = False
    st.session_state.workflow_thread = None
    st.session_state.last_update = time.time()

# Set page config
st.set_page_config(
    page_title="Engineering Design Assistant",
    page_icon="⚙️",
    layout="wide"
)

# Title and description
st.title("⚙️ Engineering Design Assistant")
st.markdown("""
This assistant helps you with engineering design tasks. Start by describing your design requirements,
and the assistant will guide you through the design process.
""")

def process_workflow_output():
    """Process workflow outputs in a background thread."""
    while not st.session_state.workflow_completed:
        try:
            # Get the current state
            current_state = st.session_state.workflow.get_state(st.session_state.workflow_config)
            st.session_state.current_state = current_state
            
            # Update active agent
            if hasattr(current_state, 'active_agent'):
                st.session_state.active_agent = current_state.active_agent
            
            # Store agent outputs
            if hasattr(current_state, 'messages'):
                for message in current_state.messages:
                    if message.role == 'assistant':
                        st.session_state.agent_outputs[st.session_state.active_agent] = message.content
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": message.content
                        })
            
            # Check if workflow is completed
            if st.session_state.active_agent == "planner":
                st.session_state.workflow_completed = True
            
            # Update timestamp
            st.session_state.last_update = time.time()
            
            # Small delay to prevent CPU overload
            time.sleep(0.1)
            
        except Exception as e:
            st.session_state.logger.write(f"Error in workflow processing: {str(e)}")
            time.sleep(1)

# Sidebar for workflow visualization and logs
with st.sidebar:
    st.header("Workflow Status")
    st.markdown(f"**Current Agent:** {st.session_state.active_agent}")
    
    if 'current_state' in st.session_state:
        st.json(st.session_state.current_state)
    
    st.header("System Logs")
    # Display new logs
    while not st.session_state.logger.output_queue.empty():
        log = st.session_state.logger.output_queue.get()
        st.text(log)

# Main content area
if not st.session_state.workflow_completed:
    # Display agent outputs
    st.header("Agent Outputs")
    for agent, output in st.session_state.agent_outputs.items():
        with st.expander(f"Output from {agent}"):
            st.markdown(output)

    # Only show chat interface during requirements phase
    if st.session_state.active_agent in ["router", "human", "requirements"]:
        st.header("Requirements Gathering")
        st.markdown("Please describe your design requirements below:")
        
        # Display chat messages
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Chat input
        if prompt := st.chat_input("Describe your design requirements"):
            # Add user message to chat
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            # Process the input through the workflow
            try:
                with contextlib.redirect_stdout(st.session_state.logger):
                    # If this is the first message, start the workflow
                    if len(st.session_state.messages) == 1:
                        response = st.session_state.workflow.invoke(
                            {"messages": [{"role": "user", "content": prompt}]},
                            config=st.session_state.workflow_config
                        )
                        # Start the background thread
                        st.session_state.workflow_thread = threading.Thread(target=process_workflow_output)
                        st.session_state.workflow_thread.daemon = True
                        st.session_state.workflow_thread.start()
                    else:
                        # Continue the conversation
                        response = st.session_state.workflow.invoke(
                            Command(resume=prompt),
                            config=st.session_state.workflow_config
                        )
                
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                st.session_state.logger.write(f"Error: {str(e)}")
    else:
        # Show progress for autonomous agents
        st.info("The agents are working on your design. Please wait...")
        
        # Auto-refresh the page every 2 seconds
        if time.time() - st.session_state.last_update > 2:
            st.rerun()
else:
    st.success("✅ Engineering workflow completed!")
    st.markdown("### Final Design Plan")
    if 'current_state' in st.session_state and hasattr(st.session_state.current_state, 'design_plan'):
        st.json(st.session_state.current_state.design_plan) 