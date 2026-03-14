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
