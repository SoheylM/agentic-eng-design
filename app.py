import streamlit as st
from workflow import initialize_workflow
from langgraph.types import Command
import uuid
import sys
from io import StringIO
import contextlib
import time
from typing import Dict, Any

# Custom logging class to capture prints
class StreamlitLogger:
    def __init__(self):
        self.logs = []
    
    def write(self, message):
        if message.strip():
            self.logs.append(message)
    
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

# Sidebar for workflow visualization and logs
with st.sidebar:
    st.header("Workflow Status")
    st.markdown(f"**Current Agent:** {st.session_state.active_agent}")
    
    if 'current_state' in st.session_state:
        st.json(st.session_state.current_state)
    
    st.header("System Logs")
    for log in st.session_state.logger.logs:
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
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Process the input through the workflow
            try:
                with contextlib.redirect_stdout(st.session_state.logger):
                    # If this is the first message, start the workflow
                    if len(st.session_state.messages) == 1:
                        response = st.session_state.workflow.invoke(
                            {"messages": [{"role": "user", "content": prompt}]},
                            config=st.session_state.workflow_config
                        )
                    else:
                        # Continue the conversation
                        response = st.session_state.workflow.invoke(
                            Command(resume=prompt),
                            config=st.session_state.workflow_config
                        )
                    
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
                
                # Rerun to update the display
                st.rerun()
            
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")
                st.session_state.logger.write(f"Error: {str(e)}")
    else:
        # Show progress for autonomous agents
        st.info("The agents are working on your design. Please wait...")
        
        # Simulate progress (you might want to replace this with actual progress tracking)
        progress_bar = st.progress(0)
        for i in range(100):
            time.sleep(0.1)
            progress_bar.progress(i + 1)
            
            # Check if workflow is completed
            if st.session_state.active_agent == "planner":
                st.session_state.workflow_completed = True
                st.rerun()
else:
    st.success("✅ Engineering workflow completed!")
    st.markdown("### Final Design Plan")
    if 'current_state' in st.session_state and hasattr(st.session_state.current_state, 'design_plan'):
        st.json(st.session_state.current_state.design_plan) 