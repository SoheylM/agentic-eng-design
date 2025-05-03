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
from data_models import State

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
    st.session_state.workflow_completed = False
    st.session_state.workflow_thread = None
    st.session_state.last_update = time.time()
    st.session_state.agent_states = {}
    st.session_state.agent_logs = {}  # Store logs for each agent
    st.session_state.agent_outputs = {}  # Store structured outputs for each agent

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

def display_agent_output(state: State):
    """Display the current agent's output in a structured way."""
    agent = state.active_agent
    
    # Display agent's logs
    if agent in st.session_state.agent_logs:
        st.subheader("📝 Agent's Thought Process")
        for log in st.session_state.agent_logs[agent]:
            st.markdown(f"`{log}`")
    
    # Display structured output
    if agent == "requirements":
        if hasattr(state, 'cahier_des_charges'):
            st.subheader("📜 Requirements Document")
            st.json(state.cahier_des_charges)
    
    elif agent == "planner":
        if hasattr(state, 'design_plan'):
            st.subheader("📋 Design Plan")
            st.json(state.design_plan)
    
    elif agent == "generation":
        if hasattr(state, 'proposals'):
            st.subheader("💡 Generated Proposals")
            for i, proposal in enumerate(state.proposals):
                with st.expander(f"Proposal {i+1}: {proposal.title}"):
                    st.markdown(proposal.content)
    
    elif agent == "reflection":
        if hasattr(state, 'proposals'):
            st.subheader("🔍 Reflection Feedback")
            for i, proposal in enumerate(state.proposals):
                if hasattr(proposal, 'feedback'):
                    with st.expander(f"Feedback on Proposal {i+1}"):
                        st.markdown(proposal.feedback)
    
    elif agent == "ranking":
        if hasattr(state, 'proposals'):
            st.subheader("🏆 Proposal Rankings")
            for i, proposal in enumerate(state.proposals):
                if hasattr(proposal, 'grade'):
                    st.markdown(f"**Proposal {i+1}**: Score {proposal.grade}")
                    if hasattr(proposal, 'ranking_justification'):
                        st.markdown(f"*Justification*: {proposal.ranking_justification}")
    
    elif agent == "evolution":
        if hasattr(state, 'proposals'):
            st.subheader("🔄 Evolved Proposals")
            for i, proposal in enumerate(state.proposals):
                if hasattr(proposal, 'evolved_content'):
                    with st.expander(f"Evolution of Proposal {i+1}"):
                        st.markdown(proposal.evolved_content)
                        if hasattr(proposal, 'evolution_justification'):
                            st.markdown(f"*Justification*: {proposal.evolution_justification}")
    
    elif agent == "meta_review":
        if hasattr(state, 'proposals'):
            st.subheader("✅ Final Review")
            for i, proposal in enumerate(state.proposals):
                if hasattr(proposal, 'status'):
                    st.markdown(f"**Proposal {i+1}**: {proposal.status}")
                    if hasattr(proposal, 'reason_for_status'):
                        st.markdown(f"*Reason*: {proposal.reason_for_status}")
    
    elif agent == "synthesizer":
        if hasattr(state, 'synthesizer_notes'):
            st.subheader("🔗 Synthesis")
            st.markdown(state.synthesizer_notes[-1])
    
    elif agent == "graph_designer":
        if hasattr(state, 'design_graph_history'):
            st.subheader("📊 Design Graph")
            current_graph = state.design_graph_history[-1]
            st.json(current_graph)

def process_workflow_output():
    """Process workflow outputs in a background thread."""
    while not st.session_state.workflow_completed:
        try:
            # Get the current state
            current_state = st.session_state.workflow.get_state(st.session_state.workflow_config)
            
            # Update active agent
            if hasattr(current_state, 'active_agent'):
                agent = current_state.active_agent
                st.session_state.active_agent = agent
                st.session_state.agent_states[agent] = current_state
                
                # Capture agent's logs
                if hasattr(current_state, 'messages'):
                    if agent not in st.session_state.agent_logs:
                        st.session_state.agent_logs[agent] = []
                    for message in current_state.messages:
                        if message.role == 'assistant':
                            st.session_state.agent_logs[agent].append(message.content)
            
            # Check if workflow is completed
            if st.session_state.active_agent == "planner":
                st.session_state.workflow_completed = True
            
            # Update timestamp
            st.session_state.last_update = time.time()
            
            # Small delay to prevent CPU overload
            time.sleep(0.1)
            
        except Exception as e:
            st.error(f"Error in workflow processing: {str(e)}")
            time.sleep(1)

# Sidebar for workflow visualization and logs
with st.sidebar:
    st.header("Workflow Status")
    st.markdown(f"**Current Agent:** {st.session_state.active_agent}")
    
    if st.session_state.active_agent in st.session_state.agent_states:
        st.json(st.session_state.agent_states[st.session_state.active_agent])
    
    st.header("System Logs")
    # Display new logs
    while not st.session_state.logger.output_queue.empty():
        log = st.session_state.logger.output_queue.get()
        st.text(log)

# Main content area
if not st.session_state.workflow_completed:
    # Display current agent's output
    if st.session_state.active_agent in st.session_state.agent_states:
        display_agent_output(st.session_state.agent_states[st.session_state.active_agent])

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
    if st.session_state.active_agent in st.session_state.agent_states:
        display_agent_output(st.session_state.agent_states[st.session_state.active_agent]) 