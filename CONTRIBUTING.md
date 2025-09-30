# Contributing to AI Agent Education Platform

First off, thank you for considering contributing to the AI Agent Education Platform! 🎉

It's people like you that make this project a great tool for educators and students worldwide. more changes

## 📋 Table of Contents dummy change

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Workflow](#development-workflow)
- [Coding Guidelines](#coding-guidelines)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Automated Code Review](#automated-code-review)
- [Community](#community)

## 📜 Code of Conduct

This project and everyone participating in it is governed by our [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior to the project maintainers.

## 🚀 Getting Started

### Prerequisites

- **Node.js** v16 or higher
- **Python** 3.9 or higher
- **PostgreSQL** v12 or higher
- **Git** for version control

### Setting Up Development Environment

1. **Fork the Repository**
   ```bash
   # Click the "Fork" button on GitHub, then clone your fork
   git clone https://github.com/YOUR_USERNAME/ai-agent-education-platform.git
   cd ai-agent-education-platform
   ```

2. **Set Up Backend**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp env_template.txt .env
   # Edit .env with your configuration
   python recreate_db.py
   python create_default_scenarios.py
   ```

3. **Set Up Frontend**
   ```bash
   cd frontend
   npm install
   ```

4. **Start Development Servers**
   ```bash
   # Terminal 1: Backend
   cd backend && python main.py
   
   # Terminal 2: Frontend
   cd frontend && npm start
   ```

## 🤝 How Can I Contribute?

### 🐛 Reporting Bugs

Before creating bug reports, please check the existing issues to avoid duplicates.

**Great Bug Reports** include:
- Clear, descriptive title
- Steps to reproduce the problem
- Expected vs actual behavior
- Screenshots/videos if helpful
- Environment details (OS, browser, versions)

### ✨ Suggesting Enhancements

Enhancement suggestions are welcome! Please:
- Use a clear, descriptive title
- Provide detailed explanation of the feature
- Explain why this would be useful to users
- Consider implementation complexity

### 💻 Code Contributions

We welcome code contributions! Areas where help is especially appreciated:

**Frontend**
- UI/UX improvements
- Accessibility enhancements
- Mobile responsiveness
- Component optimization

**Backend**
- API endpoint improvements
- Database optimizations
- AI service enhancements
- Performance improvements

**Documentation**
- README improvements
- Code comments
- API documentation
- Tutorial creation

**Testing**
- Unit tests
- Integration tests
- End-to-end tests
- Performance tests

## 🔄 Development Workflow

1. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b bugfix/issue-description
   ```

2. **Make Changes**
   - Write clear, commented code
   - Follow the coding guidelines
   - Add tests for new functionality

3. **Test Your Changes**
   ```bash
   # Backend tests
   cd backend && python -m pytest
   
   # Frontend tests
   cd frontend && npm test
   
   # Run full application
   python main.py  # Backend
   npm start       # Frontend
   ```

4. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "feat: add new agent personality options"
   ```

5. **Push and Create PR**
   ```bash
   git push origin feature/your-feature-name
   # Then create a Pull Request on GitHub
   ```

## 📝 Coding Guidelines

### Python (Backend)

- **Style Guide**: Follow [PEP 8](https://pep8.org/)
- **Formatting**: Use [Black](https://black.readthedocs.io/) for code formatting
- **Imports**: Use `isort` for import sorting
- **Type Hints**: Use type hints for function parameters and returns
- **Docstrings**: Use Google-style docstrings

```python
def create_agent(name: str, role: str, personality: str) -> Agent:
    """Create a new AI agent with specified parameters.
    
    Args:
        name: The agent's display name
        role: The agent's functional role (e.g., 'Marketing')
        personality: Description of the agent's personality
        
    Returns:
        The created Agent instance
        
    Raises:
        ValueError: If required parameters are missing
    """
    # Implementation here
```

### TypeScript/React (Frontend)

- **Style Guide**: Use [Prettier](https://prettier.io/) for formatting
- **Linting**: Follow [ESLint](https://eslint.org/) rules
- **Components**: Use functional components with hooks
- **Props**: Define clear TypeScript interfaces
- **Naming**: Use PascalCase for components, camelCase for functions

```typescript
interface AgentCardProps {
  agent: Agent;
  onConfigure: (agent: Agent) => void;
  isConfigured: boolean;
}

const AgentCard: React.FC<AgentCardProps> = ({ 
  agent, 
  onConfigure, 
  isConfigured 
}) => {
  // Component implementation
};
```

### CSS/Styling

- **Framework**: Use [TailwindCSS](https://tailwindcss.com/) utility classes
- **Responsive**: Mobile-first responsive design
- **Accessibility**: Ensure proper contrast and keyboard navigation
- **Consistency**: Follow the n-aible design system

## 📝 Commit Messages

We use [Conventional Commits](https://conventionalcommits.org/) specification:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only changes
- `style`: Formatting changes (not affecting functionality)
- `refactor`: Code changes that neither fix bugs nor add features
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to build process or auxiliary tools

**Examples:**
```
feat(agents): add personality customization options
fix(api): resolve agent creation validation error
docs(readme): update installation instructions
test(scenarios): add unit tests for scenario creation
```

## 🔍 Pull Request Process

1. **Before Submitting**
   - Ensure all tests pass
   - Update documentation if needed
   - Add tests for new functionality
   - Check that your code follows style guidelines

2. **PR Description**
   - Clear title following conventional commits
   - Detailed description of changes
   - Reference related issues (`Fixes #123`)
   - Screenshots for UI changes

3. **Automated Code Review with CodeRabbit**
   - **CodeRabbit** will automatically review your PR for:
     - Code quality and best practices
     - Security vulnerabilities
     - Performance issues
     - Documentation completeness
     - Style consistency
   - CodeRabbit provides detailed feedback and suggestions
   - Address CodeRabbit's recommendations when relevant
   - The AI review is configured for our tech stack (Python, TypeScript, React, FastAPI)

4. **Human Review Process**
   - Maintainers will review your PR after CodeRabbit
   - Address any requested changes
   - Keep the conversation constructive
   - Be patient - reviews take time!

5. **After Approval**
   - Maintainer will merge your PR
   - Your changes will be included in the next release
   - Thank you for contributing! 🎉

## 🤖 Automated Code Review

This project uses **CodeRabbit** for automated code review on all pull requests. CodeRabbit is an AI-powered code review tool that provides comprehensive feedback on your code changes.

### What CodeRabbit Reviews

CodeRabbit automatically analyzes your PR for:

**🔒 Security**
- Potential security vulnerabilities
- Authentication and authorization issues
- Data privacy concerns
- Input validation problems

**⚡ Performance**
- Code efficiency and optimization opportunities
- Memory usage patterns
- Database query optimization
- API response time improvements

**🏗️ Architecture & Best Practices**
- Code organization and structure
- Design pattern adherence
- SOLID principles compliance
- Dependency management

**📝 Code Quality**
- Code readability and maintainability
- Error handling completeness
- Type safety (TypeScript/Python)
- Documentation coverage

**🎯 Project-Specific Focus**
- Database migration safety (Alembic)
- AI agent architecture patterns
- API endpoint design consistency
- Frontend component reusability

### CodeRabbit Configuration

The CodeRabbit configuration is defined in `.coderabbit.yaml` and includes:

- **Language-specific settings** for Python, TypeScript, and JavaScript
- **Project domain awareness** for AI/ML education platforms
- **Technology stack focus** on FastAPI, React, PostgreSQL, LangChain
- **Custom review prompts** for database, API, and frontend changes

### Understanding CodeRabbit Feedback

When CodeRabbit reviews your PR, you'll see:

1. **📊 Summary**: High-level overview of the changes
2. **🔍 Detailed Analysis**: Line-by-line feedback and suggestions
3. **💡 Improvement Suggestions**: Specific recommendations for better code
4. **⚠️ Potential Issues**: Warnings about bugs or security concerns
5. **✅ Positive Feedback**: Recognition of good practices

### Responding to CodeRabbit

- **Read all feedback** carefully before responding
- **Address security and performance concerns** as high priority
- **Consider suggestions** for code quality improvements
- **Ask questions** if feedback is unclear
- **Thank CodeRabbit** for helpful suggestions! 😊

### CodeRabbit vs Human Review

- **CodeRabbit**: Catches technical issues, style problems, and common mistakes
- **Human Reviewers**: Focus on business logic, user experience, and project direction
- **Both are valuable**: CodeRabbit handles the technical details, humans handle the big picture

## 🌟 Recognition

Contributors will be recognized in:
- `CONTRIBUTORS.md` file
- Release notes for significant contributions
- Special mentions in project announcements

## 🆘 Getting Help

- **GitHub Issues**: For bugs and feature requests
- **GitHub Discussions**: For questions and general discussion
- **Documentation**: Check the Wiki for detailed guides

## 📚 Learning Resources

**AI & Education**
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [Educational Technology Best Practices](https://www.edtechreview.in/)

**Technical Skills**
- [FastAPI Tutorial](https://fastapi.tiangolo.com/tutorial/)
- [React Documentation](https://react.dev/)
- [TailwindCSS Docs](https://tailwindcss.com/docs)
- [PostgreSQL Tutorial](https://www.postgresql.org/docs/)

## 🎯 Project Goals

Remember our mission: **Empowering educators to create dynamic, AI-powered business simulations that prepare students for the future of work.**

Every contribution, no matter how small, helps achieve this goal!

---

Thank you for contributing to the AI Agent Education Platform! 🙏

*Together, we're building the future of AI-powered education.* 
