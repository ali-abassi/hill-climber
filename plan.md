# Workbench and adaptive guidance

Dogfood project `hill-climber-workbench` owns the structured task and QA record.
The task `adaptive-workbench` covers:

- A responsive planning, results and guide interface at 1280 and 390 wide.
- Six editable task recipes and a truthful bounded terminal handoff.
- Verified candidate, promotion and patch evidence with safe error states.
- Compact adaptive candidate/assistant instructions and worked evaluator recipes.

Check: `npm run check` and `npm audit --omit=dev`. Browser checks must cover
recipe changes, custom budgets, command preparation/copy/brief, valid and invalid
inspection, retained versus promoted results, feedback, guide and narrow layout.
Acceptance requires the current-checkout Dogfood task and page gates. The local
workbench ships as `hill-climber ui`; it does not require a cloud deployment.
