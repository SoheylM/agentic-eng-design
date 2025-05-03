import streamlit as st
from workflow import initialize_workflow
from langgraph.types import Command
import uuid

# Initialize session state
if 'workflow' not in st.session_state:
    st.session_state.workflow = initialize_workflow()
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.workflow_config = {
        "configurable": {"thread_id": st.session_state.thread_id},
        "recursion_limit": 500
    }

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

# Sidebar for workflow visualization
with st.sidebar:
    st.header("Workflow Status")
    # Here you could add a visualization of the workflow graph
    # For now, we'll just show the current state
    if 'current_state' in st.session_state:
        st.json(st.session_state.current_state)

# Main chat interface
st.header("Design Assistant Chat")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("Describe your design requirements or provide feedback"):
    # Add user message to chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Process the input through the workflow
    try:
        # If this is the first message, start the workflow
        if len(st.session_state.messages) == 1:
            response = st.session_state.workflow.invoke(
                {"messages": [prompt]},
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
        
        # Display the response
        if 'messages' in current_state:
            for message in current_state['messages']:
                if message['role'] == 'assistant':
                    st.session_state.messages.append(message)
                    with st.chat_message("assistant"):
                        st.markdown(message['content'])
    
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")

# Add a button to end the session
if st.button("End Session"):
    st.session_state.workflow.invoke(
        Command(update={"active_agent": "planner"}),
        config=st.session_state.workflow_config
    )
    st.success("Session ended. Moving to planning phase.")
    st.rerun() 