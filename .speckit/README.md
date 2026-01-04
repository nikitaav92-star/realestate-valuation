# SpecKit Integration Guide

This directory contains GitHub SpecKit files for AI-assisted development.

## What is SpecKit?

SpecKit is GitHub's open-source toolkit for **Spec-Driven Development** - writing detailed specifications before generating code with AI. It helps keep AI-generated code aligned with project requirements.

## Directory Structure

```
.speckit/
├── constitution/          # Project governance & principles
│   └── project-constitution.md
├── specifications/        # Feature specifications (TBD)
├── plans/                # Implementation plans (TBD)
├── tasks/                # Task tracking
│   └── current-sprint.md
├── bugs/                 # Bug reports
│   └── incomplete-data.md
├── ideas/                # Improvement backlog
│   └── improvements-backlog.md
└── PROJECT-MAP.md        # Codebase navigation guide
```

## Quick Start

### 1. Using SpecKit Commands (in AI chat)

SpecKit provides slash commands for AI assistants:

```
/speckit.constitution  # View project principles
/speckit.tasks         # See current sprint tasks
/speckit.bugs          # List open bugs
/speckit.ideas         # Browse improvement ideas
/speckit.implement TASK-001  # Auto-implement a task
```

### 2. Creating New Tasks

Add tasks to `.speckit/tasks/current-sprint.md`:

```markdown
### TASK-XXX: Task Title
**Priority:** P0 (Critical) | P1 (High) | P2 (Medium)
**Effort:** X hours
**Status:** 🔴 Blocked | 🟡 In Progress | 🟢 Ready

**Objective:** What needs to be done

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2

**Implementation Steps:**
1. Step 1
2. Step 2
```

### 3. Reporting Bugs

Create a file in `.speckit/bugs/`:

```markdown
# Bug: Title

**Status:** Open | In Progress | Fixed
**Priority:** P0 | P1 | P2
**Created:** YYYY-MM-DD

## Description
What's wrong?

## Impact
How does this affect users?

## Root Cause
Why is this happening?

## Proposed Solution
How to fix it?

## Test Cases
How to verify the fix?
```

### 4. Adding Ideas

Update `.speckit/ideas/improvements-backlog.md`:

```markdown
### N. Idea Title
**Status:** Idea | Planned | In Progress
**Effort:** Small | Medium | Large
**Impact:** Low | Medium | High

**Description:** What is the idea?

**Benefits:** Why should we do this?

**Implementation:** How would we build it?
```

## Integration with AI Tools

### Claude Code

Claude Code automatically reads SpecKit files when you:
1. Ask about project structure: "What's the architecture?"
2. Request bug fixes: "Fix the incomplete data issue"
3. Implement features: "Implement TASK-001"

### Context7 MCP

Context7 (`.context7.yaml`) indexes SpecKit files for smart context injection:

```yaml
# In .context7.yaml
search:
  topic_mapping:
    bugs: [".speckit/bugs/"]
    tasks: [".speckit/tasks/"]
    architecture: [".speckit/constitution/"]
```

When you mention "bugs" or "tasks" in prompts, Context7 injects relevant SpecKit docs.

### Cursor IDE

Cursor can use SpecKit commands via MCP integration:

1. Install Context7 MCP:
   ```bash
   npx -y @smithery/cli install @upstash/context7-mcp --client cursor
   ```

2. Add to Cursor settings (Ctrl+Shift+P → "Cursor Settings"):
   ```json
   {
     "mcpServers": {
       "context7": {
         "command": "npx",
         "args": ["-y", "@upstash/context7-mcp"]
       }
     }
   }
   ```

3. Use in prompts: "use context7 to show me TASK-001"

## Workflow

### Starting a New Feature

1. **Write Specification** (`.speckit/specifications/feature-name.md`)
   - What: Feature description
   - Why: User value & business case
   - How: Technical approach
   - Acceptance: Definition of done

2. **Create Implementation Plan** (`.speckit/plans/feature-name.md`)
   - Tech stack choices
   - Architecture decisions
   - File changes needed
   - Migration plan

3. **Break into Tasks** (`.speckit/tasks/`)
   - Create TASK-XXX for each step
   - Estimate effort
   - Prioritize

4. **Implement with AI**
   ```
   /speckit.implement TASK-XXX
   ```

5. **Track Progress**
   - Update task status as you work
   - Move to "Completed" when done

### Bug Fixing Workflow

1. **Report Bug** (`.speckit/bugs/bug-name.md`)
   - Reproduce steps
   - Root cause analysis
   - Proposed fix

2. **Create Task** (`.speckit/tasks/`)
   - Link to bug report
   - Add test cases

3. **Implement Fix**
   ```
   /speckit.implement TASK-XXX
   ```

4. **Verify & Close**
   - Run test cases
   - Update bug status to "Fixed"

## Best Practices

### Writing Good Specifications

✅ **Do:**
- Be specific about requirements
- Include acceptance criteria
- Add code examples
- Link to related issues

❌ **Don't:**
- Write vague descriptions
- Skip test cases
- Forget to update status
- Mix multiple concerns

### Task Naming

Format: `TASK-XXX: <Verb> <Noun>`

Examples:
- ✅ `TASK-001: Fix OfferSubtitle parsing`
- ✅ `TASK-002: Add price drop alerts`
- ❌ `TASK-003: Parser issues`
- ❌ `TASK-004: Improvements`

### Commit Messages

Link commits to SpecKit tasks:

```bash
git commit -m "fix(parser): extract rooms from OfferSubtitle

Fixes incomplete data parsing issue (TASK-001).

- Check both OfferTitle and OfferSubtitle
- Prefer subtitle if it contains property details
- Add regex-based heuristic for promotional text

Closes: .speckit/bugs/incomplete-data.md
Implements: .speckit/tasks/current-sprint.md TASK-001"
```

## Resources

- [GitHub SpecKit Repository](https://github.com/github/spec-kit)
- [Context7 Documentation](https://github.com/upstash/context7)
- [Spec-Driven Development Guide](https://medium.com/@abhinav.dobhal/revolutionizing-ai-powered-development-a-complete-guide-to-githubs-speckit-a85a39f0e2ee)

## Maintenance

### Weekly Review

1. Update task statuses
2. Archive completed tasks
3. Prioritize backlog
4. Add new ideas from retrospectives

### Monthly Cleanup

1. Move old bugs to `archive/`
2. Update constitution if principles changed
3. Refresh project map
4. Review and update tech stack

---

**Last updated:** 2025-11-03  
**Maintained by:** Project Team
