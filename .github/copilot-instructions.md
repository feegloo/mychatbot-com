# Copilot Workspace Instructions for ChatRAG Hybrid RAG App

## Purpose
These instructions guide AI agents (like GitHub Copilot) to be productive and consistent in the ChatRAG Hybrid RAG App workspace. They summarize architecture, conventions, and key workflows, and link to detailed docs where needed.
---

## General AI model guidelines
- take your time, code quality is most important
- i want you to create code as "high-performer" developer, who is careful, thoughtful, and prioritizes maintainability and readability over speed or cleverness
- reason slowly and carefully, and try to understand the context and requirements before generating code or suggestions
- avoid hallucinating information or making assumptions about the codebase, architecture, or requirements that aren't supported by the existing documentation or code
- when in doubt, ask for clarification or link to relevant documentation rather than making assumptions
- ask for input in interactive way, by asking questions or requesting more information, rather than making assumptions or generating code that may not fit the actual requirements or context
- check README.md for code snippets useful for debugging production logs, and create more by youself if needed, to help with debugging and understanding the system, especially for complex areas like the AI engine and vector store interactions
- use Sentry MCP as well to check projects (I configured Sentry for both frontend and backend, so you can check error logs and performance metrics there to help with debugging and understanding the system's behavior in production
- you should be independent and proactive in finding information and understanding the codebase, architecture, and requirements, and should not rely on me to provide all the information or context you need to be productive
- after round of few AI Agents implementations, you can ask to run ./deploy, to see how your changes work in production, and to check logs and Sentry for any errors or issues that may arise, and use that information to further improve your understanding of the system and to guide your future implementations and contributions, ocassionally propose me to run ./deploy (but never run ./deploy yourself), periodically check status of process running in the background, tell me it's finished, and if it fails, try to understand the error message and reason about what might be causing it, and ask for clarification or suggest potential solutions based on the error message and your understanding of the codebase and architecture
- always install necessary dependencies and set up the environment properly before trying to run any commands or scripts, to avoid unnecessary errors and issues that can arise from missing dependencies or misconfigured environments
- install node modules for both frontend and backend, and install python dependencies as well, to ensure you have all the necessary tools and libraries to run the system and to be productive in your work, but remember to keep package-lock.json and requirements.txt files up-to-date with any changes to dependencies, to help ensure consistency and reproducibility across different environments and setups
- always modify .env for dev and .env for production by yourself, but you can comment previous env if it's valueable and shouldn't be lost, but generally add required .env to deploy to production, when you obtain some tocken
- try to execute as many cli commands as possible by yourself (main system: macOS), to understand the system better, and to be more independent in your work, but if you encounter any issues or errors while running commands, try to understand the error message and reason about what might be causing it, and ask for clarification or suggest potential solutions based on the error message and your understanding of the codebase and architecture
- use as many MCP integrations or install them along the way, to help with debugging, understanding the system, and improving your productivity and independence in the workspace
- if user uploads screenshot with visible url of browser or sends URL link, visit URL to get HTML and CSS content, and use it to understand the issue better, and to provide more accurate suggestions or code snippets to help with the issue, but also be mindful of privacy and security concerns when accessing user-provided URLs, and ensure that you are not accessing any sensitive or private information without proper authorization or consentss


---

## Architecture Overview
- **Frontend:** Vue 3 + TypeScript ([frontend/](frontend/))
- **Backend:** Node.js + Koa + TypeScript ([backend/](backend/))
- **Python AI Engine:** LangChain, Jupyter notebooks, and scripts ([python/](python/))
- **Vector DB:** Chroma
- **Metadata DB:** PostgreSQL
- See [ARCHITECTURE.md](ARCHITECTURE.md) for diagrams and details.

---

## Build & Test Commands
- **Frontend:**
  - Install: `cd frontend && npm install`
  - Dev: `npm run dev`
  - Test: `npm run test` or `npm run test:unit`
- **Backend:**
  - Install: `cd backend && npm install`
  - Dev: `npm run dev`
  - Test: `npm run test` or `npm run test:unit`
- **Python:**
  - Install: `cd python && pip install -r requirements.txt`
  - Index: `python index_documents.py ...`
  - Answer: `python answer_question.py ...`
  - See [python/README.md](python/README.md) for notebook and script usage.
  - in CLI, we are using explicitly `python3.11` instead of `python`, to make sure we are using correct version of python, and avoid any issues with multiple python versions installed on the system, so you should do the same when running python scripts or commands, to ensure consistency and avoid potential issues with using the wrong python version or environment
--- 

Deployment:

./deploy will "hang in console" falsly waiting for process to finish, but it actually finishes and you can check GCP logs in Sentry or by running `docker-compose logs -f` to see the output of the backend and frontend containers, and to check for any errors or issues that may arise during deployment or when running the system in production. If you encounter any errors or issues, try to understand the error message and reason about what might be causing it, and ask for clarification or suggest potential solutions based on the error message and your understanding of the codebase and architecture.


---

## Key Conventions
- **Link, don’t embed:** Reference docs like [ARCHITECTURE.md](ARCHITECTURE.md) and [python/README.md](python/README.md) instead of duplicating content.
- **Indexing:** Use Python scripts for production, notebooks for experimentation.
- **File Uploads:** Handled by backend, stored on disk (can be swapped for S3).
- **Vector Store:** Chroma collections are per conversation.
- **Shareable URLs:** Format: `/c/<conversationId>`

---

## Potential Pitfalls
- Ensure Python and Node environments are set up before running scripts.
- Chroma and PostgreSQL must be running for full functionality (see docker-compose.yml).
- For cloud deploy, see [infra/cloudrun/README.md](infra/cloudrun/README.md).

---

## Documentation Links
- [README.md](README.md) for project overview and setup instructions.
- [ARCHITECTURE.md](ARCHITECTURE.md): Full system architecture
- [python/README.md](python/README.md): Python engine usage
- [infra/cloudrun/README.md](infra/cloudrun/README.md): GCP deployment

---

## Example Prompts
- "How do I run the backend tests?"
- "Where is the Python indexing logic?"
- "How do I deploy to GCP?"

---

## Next Steps
- For area-specific instructions, consider adding `applyTo`-based customizations for frontend, backend, or python.
- To extend agent behavior, see [agent-customization skill](https://github.com/features/copilot#customization) or create `/create-instruction`, `/create-agent`, or `/create-skill` files as needed.


## Code Guidelines
- Follow existing code style and patterns in each area (frontend, backend, python).
- For new features, look for similar existing implementations and follow their structure.
- When in doubt, link to documentation or ask for clarification rather than making assumptions.
- code quality and maintainability are priorities, so prefer clear and consistent code over clever but obscure solutions.
- minimalist and straightforward implementations are preferred, especially in the backend and python where performance and reliability are key.
- prefer pure functions over unpure stateful ones - keep pure functions in utils.ts or similar, and keep stateful logic in index.ts or main component files which uses those pure functions by providing necessary state and context, to keep code organized and maintainable
- take your time to understand the existing code and architecture before making changes, especially for complex areas like the AI engine and vector store interactions.
- writing as much less code as possible to achieve the same functionality is often better, as long as it remains clear and maintainable.
- always try to add or update tests when making changes, to ensure the system remains robust and to help future developers understand the intended behavior (unit, e2e, or integration tests as appropriate for the change).
- when updating documentation, ensure it remains accurate and up-to-date with the current state of the codebase, and consider adding examples or clarifications if it can help future developers understand the system better.
- preffer instead of lot's of comments, suitable names of variables, functions, and classes that can explain their purpose and usage
- if you need to add comments, make sure they are clear, concise, and provide value beyond what the code itself can convey (e.g., explaining why a certain approach was taken, or any non-obvious implications of the code)
- comment should explain edge cases, assumptions, or any important context that isn't immediately clear from the code itself, rather than stating the obvious or repeating what the code already says
- for the frontend, follow the existing component structure and styling conventions, and prefer composition and reusability when creating new components or features over claass-based components or tightly coupled code
- centralize error propagation, so error always "bubble up" to the top-level handler in the backend, and to a global error handler in the frontend, to ensure consistent error handling and reporting across the system
- errors should be catched by Sentry, displayed to users in a user-friendly way, and include as much relevant context as possible to help with debugging and resolution (e.g., error messages, stack traces, relevant state or input data, etc.), but also displayed in console logs for developers to see during development and debugging with clear error
- debug information should be logged to the console during development, but should be removed or minimized in production code to avoid cluttering logs and potentially exposing sensitive information
- if possible, refactor code in areas you are currently implementing feature, to be more testable, by breaking down complex functions into smaller, more focused ones, and by using dependency injection or other techniques to make it easier to mock dependencies in tests
- simplify code : start with index.ts / Component.vue, then break down into smaller files if it grows too large , like utils.ts, consts.ts, composables.ts, or other custom .ts names, extracting code from index.ts / Component.vue
- for Vue.js - avoid nextTick() if possible, and prefer using reactive state and computed properties to manage updates and reactivity, as it can lead to cleaner and more maintainable code, and can help avoid potential issues with timing and state consistency that can arise with nextTick()
- Vue:js - regularly extract smaller components if code is copy pasted or suits more than one component to share logic,
- Vue.js - extract reusable "dumb" components like Button.vue, Checkbox.vue, Modal.vue, TextField.vue, etc, in separate scope, which are imported by "View" components (having business logic) 
- preffer "style" attribute temporarly for small styling, but for larger or shared styles, consider using CSS classes or scoped styles in Vue components to keep styling organized and maintainable
- re-adjust and reorganize CSS classes and styles as needed when implementing new features, to ensure the UI remains consistent and visually appealing, and to avoid duplication or conflicts in styles across different components or areas of the application
- always try to imporove unit tests by properl using mocks, keeping with convention of test frameworks (Vitest, etc),
  and write meaningful test about implementation you are contributing to codabase
- adhere to best practices for security, performance, and scalability, especially in the backend and python code, to ensure the system remains robust and can handle production workloads effectively
- adhere to code patterns like DDD (Domain-Driven Design), Law of Demeter, KISS (Keep It Simple, Stupid), DRY (Don't Repeat Yourself), YAGNI (You Aren't Gonna Need It), and other relevant design principles and patterns to ensure the codebase remains clean, maintainable, and scalable as it evolves over time
- constantly improve coding setup and DX by installing helpful extensions, linters, formatters, and other tools that can help with code quality, consistency, and productivity, but also ensure that these tools are properly configured and integrated into the development workflow to avoid unnecessary friction or issues
- see skill "/refactor" , like "/refactor frontend" or "/refactor all" - use it from time to time