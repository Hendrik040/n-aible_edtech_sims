# 🤖 AI Agents Guide

## Overview

The AI Agent Education Platform uses specialized AI agents powered by LangChain to provide intelligent, context-aware interactions in educational simulations. Each agent has specific responsibilities and capabilities designed to enhance the learning experience.

## 🏗️ Agent Architecture

### LangChain Integration
- **Framework**: Professional AI agent orchestration using LangChain
- **Centralized Management**: All agents managed through a unified system
- **Memory Systems**: Persistent memory and context across interactions
- **Tool Integration**: Agents can use various tools and external services

### Agent Types
- **Persona Agent**: Handles character-specific interactions
- **Summarization Agent**: Provides content analysis and summarization
- **Grading Agent**: Assesses student performance and provides feedback
- **Session Agent**: Manages conversation state and context

## 👤 Persona Agent

### Purpose
The Persona Agent is responsible for maintaining consistent, personality-driven interactions with AI characters in business simulations.

### Key Features
- **Personality Consistency**: Maintains character traits across all interactions
- **Context Awareness**: Remembers previous conversations and decisions
- **Role-Based Responses**: Responds according to the character's business role
- **Emotional Intelligence**: Adapts responses based on conversation context

### Implementation
```python
from modules.simulation.agents.persona_agent import PersonaAgent

# Initialize persona agent
persona_agent = PersonaAgent(
    persona_id="cto_mike",
    personality_traits={
        "analytical": 9,
        "creative": 7,
        "assertive": 8
    },
    background="Experienced CTO with 15 years in tech"
)

# Process user interaction
response = await persona_agent.process_message(
    message="What's your opinion on the current market situation?",
    context={"scene_id": 1, "user_progress": "beginner"}
)
```

### Personality Traits
- **Analytical**: Logical, data-driven decision making
- **Creative**: Innovative thinking and problem-solving
- **Assertive**: Confident, direct communication style
- **Collaborative**: Team-oriented, consensus-building approach
- **Detail-Oriented**: Focus on specifics and thoroughness

### Memory Management
- **Conversation History**: Maintains context from previous interactions
- **Decision Tracking**: Remembers choices made in the simulation
- **Relationship Dynamics**: Tracks relationships with other personas
- **Learning Adaptation**: Adjusts responses based on user learning style

## 📝 Summarization Agent

### Purpose
The Summarization Agent analyzes conversation content and provides intelligent summaries, key point extraction, and progress tracking.

### Key Features
- **Content Analysis**: Identifies key points and important information
- **Progress Summaries**: Tracks learning progress and achievements
- **Insight Generation**: Extracts meaningful insights from conversations
- **Learning Outcome Tracking**: Monitors progress toward learning objectives

### Implementation
```python
from modules.simulation.agents.summarization_agent import SummarizationAgent

# Initialize summarization agent
summary_agent = SummarizationAgent(
    learning_objectives=[
        "Understand market analysis techniques",
        "Develop strategic thinking skills"
    ]
)

# Generate conversation summary
summary = await summary_agent.analyze_conversation(
    conversation_history=conversation_text,
    scene_id=1,
    user_id=123
)
```

### Analysis Capabilities
- **Key Point Extraction**: Identifies the most important information
- **Progress Assessment**: Evaluates learning progress and comprehension
- **Gap Analysis**: Identifies areas where additional learning is needed
- **Recommendation Generation**: Suggests next steps for continued learning

### Output Formats
- **Executive Summary**: High-level overview of conversation content
- **Key Takeaways**: Bullet points of important information
- **Progress Report**: Detailed analysis of learning progress
- **Action Items**: Specific recommendations for continued learning

## 📊 Grading Agent

### Purpose
The Grading Agent assesses student performance, provides detailed feedback, and tracks learning outcomes throughout the simulation.

### Key Features
- **Performance Assessment**: Evaluates student responses and decisions
- **Feedback Generation**: Provides constructive, actionable feedback
- **Learning Objective Tracking**: Monitors progress toward specific goals
- **Adaptive Scoring**: Adjusts assessment based on student level and context

### Implementation
```python
from modules.simulation.agents.grading_agent import GradingAgent

# Initialize grading agent
grading_agent = GradingAgent(
    assessment_criteria={
        "market_analysis": 0.3,
        "strategic_thinking": 0.4,
        "communication": 0.3
    }
)

# Assess student performance
assessment = await grading_agent.assess_performance(
    student_responses=responses,
    scene_objectives=objectives,
    context=simulation_context
)
```

### Assessment Criteria
- **Analytical Thinking**: Quality of analysis and reasoning
- **Strategic Planning**: Ability to develop and execute strategies
- **Communication Skills**: Clarity and effectiveness of communication
- **Problem Solving**: Approach to identifying and solving problems
- **Business Acumen**: Understanding of business concepts and practices

### Feedback Types
- **Immediate Feedback**: Real-time responses to student actions
- **Comprehensive Reviews**: Detailed analysis of overall performance
- **Progress Reports**: Regular updates on learning progress
- **Recommendation Letters**: Suggestions for continued improvement

## 🧠 Session Agent

### Purpose
The Session Agent manages conversation state, context, and memory across multiple interactions and sessions.

### Key Features
- **State Management**: Maintains conversation state across sessions
- **Context Preservation**: Ensures continuity in multi-session simulations
- **Memory Integration**: Combines short-term and long-term memory
- **Performance Optimization**: Efficient memory usage and retrieval

### Implementation
```python
from modules.simulation.agents.session_agent import SessionAgent

# Initialize session agent
session_agent = SessionAgent(
    session_id="user_123_scenario_456",
    memory_type="conversation_buffer"
)

# Manage session state
state = await session_agent.update_state(
    new_interaction=interaction,
    context=current_context
)
```

### Memory Types
- **Conversation Buffer**: Recent conversation history
- **Summary Buffer**: Compressed long-term memory
- **Vector Memory**: Semantic search and retrieval
- **Episodic Memory**: Specific event and interaction memory

### State Management
- **Session Persistence**: Maintains state across browser sessions
- **Context Switching**: Handles transitions between different scenarios
- **Memory Consolidation**: Combines and organizes different memory types
- **Cleanup Management**: Efficient memory cleanup and optimization

## 🔧 Agent Configuration

### Environment Variables
```env
# OpenAI Configuration
OPENAI_API_KEY=<your_openai_api_key>

# LangChain Configuration
LANGCHAIN_OPENAI_API_KEY=your_openai_api_key
LANGCHAIN_OPENAI_MODEL=gpt-4o
LANGCHAIN_EMBEDDING_MODEL=text-embedding-3-small

# Agent Settings
LANGCHAIN_AGENT_TEMPERATURE=0.7
LANGCHAIN_AGENT_MAX_TOKENS=1000
LANGCHAIN_MEMORY_WINDOW_SIZE=10
LANGCHAIN_CACHE_TTL=1800
```

### Agent Initialization
```python
from langchain_config import langchain_manager

# Access global LangChain manager
llm = langchain_manager.llm
embeddings = langchain_manager.embeddings
vectorstore = langchain_manager.vectorstore

# Initialize agents with shared resources
persona_agent = PersonaAgent(llm=llm, memory=vectorstore)
summary_agent = SummarizationAgent(llm=llm, embeddings=embeddings)
grading_agent = GradingAgent(llm=llm, vectorstore=vectorstore)
```

## 🚀 Creating Custom Agents

### Agent Base Class
```python
from langchain.agents import BaseAgent
from langchain.schema import BaseMessage

class CustomAgent(BaseAgent):
    def __init__(self, agent_type: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_type = agent_type
        self.llm = langchain_manager.llm
        
    async def process_message(self, message: str, context: dict):
        # Custom agent logic here
        pass
        
    async def get_memory(self, query: str):
        # Memory retrieval logic
        pass
        
    async def update_memory(self, content: str, metadata: dict):
        # Memory update logic
        pass
```

### Agent Registration
```python
from services.session_manager import SessionManager

# Register custom agent
session_manager = SessionManager()
session_manager.register_agent(
    agent_type="custom_agent",
    agent_class=CustomAgent,
    config={"temperature": 0.8}
)
```

### Agent Tools
```python
from langchain.tools import BaseTool

class CustomTool(BaseTool):
    name = "custom_tool"
    description = "Description of what this tool does"
    
    def _run(self, query: str) -> str:
        # Tool implementation
        return "Tool result"
        
    async def _arun(self, query: str) -> str:
        # Async tool implementation
        return "Async tool result"
```

## 📊 Agent Performance Monitoring

### Metrics Tracking
- **Response Time**: Time taken to generate responses
- **Token Usage**: Number of tokens consumed per interaction
- **Memory Usage**: Amount of memory used for context storage
- **Error Rates**: Frequency of agent errors and failures

### Performance Optimization
- **Caching**: Cache frequently used responses and context
- **Batch Processing**: Process multiple requests together when possible
- **Memory Management**: Efficient memory usage and cleanup
- **Load Balancing**: Distribute agent load across multiple instances

### Monitoring Tools
```python
from modules.simulation.agents.monitoring import AgentMonitor

# Initialize monitoring
monitor = AgentMonitor()

# Track agent performance
await monitor.track_interaction(
    agent_type="persona_agent",
    response_time=0.5,
    token_count=150,
    success=True
)

# Get performance metrics
metrics = await monitor.get_metrics(
    agent_type="persona_agent",
    time_range="last_24_hours"
)
```

## 🔒 Agent Security

### Input Validation
- **Content Filtering**: Filter inappropriate or harmful content
- **Rate Limiting**: Prevent abuse and excessive usage
- **Input Sanitization**: Clean and validate all user inputs
- **Context Validation**: Ensure context data is valid and safe

### Privacy Protection
- **Data Encryption**: Encrypt sensitive data in memory and storage
- **Access Control**: Restrict agent access to authorized users only
- **Audit Logging**: Log all agent interactions for security monitoring
- **Data Retention**: Implement proper data retention and cleanup policies

### Error Handling
- **Graceful Degradation**: Handle errors without breaking the user experience
- **Fallback Responses**: Provide default responses when agents fail
- **Error Recovery**: Automatic recovery from transient failures
- **User Notification**: Inform users of issues in a user-friendly way

## 🧪 Testing Agents

### Unit Testing
```python
import pytest
from modules.simulation.agents.persona_agent import PersonaAgent

@pytest.mark.asyncio
async def test_persona_agent_response():
    agent = PersonaAgent(persona_id="test_persona")
    response = await agent.process_message(
        "Hello, how are you?",
        context={"scene_id": 1}
    )
    assert response is not None
    assert len(response) > 0
```

### Integration Testing
```python
@pytest.mark.asyncio
async def test_agent_integration():
    # Test agent interaction with database
    # Test agent memory persistence
    # Test agent context management
    pass
```

### Performance Testing
```python
@pytest.mark.asyncio
async def test_agent_performance():
    # Test response times
    # Test memory usage
    # Test concurrent request handling
    pass
```

## 📚 Best Practices

### Agent Design
- **Single Responsibility**: Each agent should have a clear, focused purpose
- **Stateless Design**: Minimize stateful behavior for better scalability
- **Error Handling**: Implement comprehensive error handling and recovery
- **Documentation**: Document agent behavior and configuration options

### Performance
- **Async Operations**: Use async/await for all I/O operations
- **Memory Management**: Implement efficient memory usage and cleanup
- **Caching**: Cache frequently used data and responses
- **Monitoring**: Track performance metrics and optimize based on data

### Security
- **Input Validation**: Validate and sanitize all inputs
- **Access Control**: Implement proper authentication and authorization
- **Data Protection**: Encrypt sensitive data and implement privacy controls
- **Audit Logging**: Log all agent interactions for security monitoring

---

*For technical implementation details, see the [Developer Guide](Developer_Guide.md) and [API Reference](API_Reference.md).*
