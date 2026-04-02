# AI Development Guidelines

To maintain code quality and adhere to project standards, please follow these instructions for every session:

## Linting & Quality Control
* **Automatic Check:** For every change made to Python files, you must always run `ruff check`.
* **Fixing Issues:** If `ruff` identifies any violations, please address them immediately before presenting the final code.
* **Formatting:** If `ruff format` is available in the environment, please run that as well to ensure PEP 8 compliance.
* **Tests:** Run all tests make sure all tests passes.

## Workflow Integration
1.  Modify the code as requested.
2.  Add new tests covering the new changes.
3.  Execute `ruff check .` in the terminal.
4.  Review output; if errors exist, iterate on the code until all issues are addressed.
5.  Make sure all tests passes, iterate until all tests are successful.
6.  Commit the change and push to the repo.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
