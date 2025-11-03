# Context7 MCP Setup Guide

Context7 is an MCP (Model Context Protocol) server that provides up-to-date, version-specific documentation to AI coding assistants.

## What Does Context7 Do?

When you use AI assistants like Claude Code or Cursor, Context7 automatically:
1. **Indexes your codebase** using `.context7.yaml` configuration
2. **Injects relevant context** when you mention topics (bugs, tasks, architecture)
3. **Provides smart navigation** through topic mapping and file prioritization
4. **Keeps docs fresh** with 1-hour cache TTL

## Prerequisites

- **Node.js** 18+ installed
- AI coding tool that supports MCP:
  - Claude Desktop
  - Cursor IDE
  - Windsurf
  - VS Code with MCP extension

## Installation

### For Claude Desktop (Recommended)

```bash
npx -y @smithery/cli install @upstash/context7-mcp --client claude
```

This automatically:
- Installs Context7 MCP server
- Configures Claude Desktop settings
- Enables "use context7" in prompts

### For Cursor IDE

1. **Open Cursor Settings**
   - Press `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (Mac)
   - Type "Cursor Settings" and open the settings file

2. **Add MCP Configuration**
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

3. **Restart Cursor**

4. **Test Integration**
   In Cursor chat, type:
   ```
   use context7 to show me the project structure
   ```

### For Windsurf

Same as Cursor - add MCP config to Windsurf settings.

### For VS Code

1. **Install MCP Extension** (if available)
   
2. **Configure in settings.json**
   ```json
   {
     "mcp.servers": {
       "context7": {
         "command": "npx",
         "args": ["-y", "@upstash/context7-mcp"]
       }
     }
   }
   ```

## Configuration

Context7 reads `.context7.yaml` from your project root. See [../.context7.yaml](../.context7.yaml) for our configuration.

### Key Configuration Sections

#### 1. Indexing Rules
```yaml
index:
  include: ["etl/", "db/", "tests/"]
  exclude: ["**/__pycache__", "**/venv"]
  extensions: [".py", ".sql", ".md"]
```

#### 2. Topic Mapping
```yaml
search:
  topic_mapping:
    parsing: ["etl/collector_cian/browser_fetcher.py"]
    bugs: [".speckit/bugs/"]
    tasks: [".speckit/tasks/"]
```

When you mention "parsing" in a prompt, Context7 injects `browser_fetcher.py` context.

#### 3. Entry Points
```yaml
documentation:
  entry_points:
    - etl/collector_cian/cli.py
    - db/schema.sql
  
  always_include:
    - .speckit/constitution/project-constitution.md
    - README.md
```

These files are prioritized when AI needs to understand the project.

## Usage

### Basic Usage

In your AI assistant chat:

```
use context7 to explain the parsing logic
```

Context7 will:
1. Find relevant files (browser_fetcher.py, mapper.py)
2. Inject their content into the prompt
3. Provide up-to-date code examples

### Advanced Usage

#### Show Current Tasks
```
use context7 to list current sprint tasks
```

#### Explain Architecture
```
use context7 to explain the anti-bot strategy
```

#### Fix Bugs
```
use context7 to show bug TASK-001 and implement a fix
```

#### Navigate Code
```
use context7 to find where prices are upserted to database
```

## Verification

### Check if Context7 is Running

In your AI assistant, run:
```
@context7 status
```

You should see:
- ✅ Context7 MCP server running
- ✅ Indexed N files
- ✅ Configuration loaded from .context7.yaml

### Test Topic Mapping

Try these prompts:

1. **"use context7 to explain parsing"**
   - Should inject `browser_fetcher.py`

2. **"use context7 to show bugs"**
   - Should inject `.speckit/bugs/incomplete-data.md`

3. **"use context7 to show tasks"**
   - Should inject `.speckit/tasks/current-sprint.md`

## Troubleshooting

### Context7 Not Found

**Symptom:** AI says "I don't have access to context7"

**Fix:**
```bash
# Reinstall Context7
npx -y @smithery/cli install @upstash/context7-mcp --client <your-client>

# Or manually
npm install -g @upstash/context7-mcp
```

### Configuration Not Loading

**Symptom:** Topic mapping doesn't work

**Fix:**
1. Verify `.context7.yaml` exists in project root
2. Check YAML syntax (use yamllint or online validator)
3. Restart your AI coding tool

### Slow Performance

**Symptom:** Context7 takes >5 seconds to respond

**Fix:**
1. Reduce `index.include` paths (only index necessary directories)
2. Add more patterns to `index.exclude`
3. Lower `cache.ttl` to use cached data more often

### Files Not Being Indexed

**Symptom:** Context7 doesn't find your files

**Fix:**
1. Check `index.extensions` includes your file types
2. Ensure files aren't in `index.exclude` patterns
3. Re-index: restart AI tool or clear cache

## Advanced Features

### API Key (Optional)

For enhanced features (e.g., cloud caching), get an API key:

1. Visit [context7.com/dashboard](https://context7.com/dashboard)
2. Create account and generate API key
3. Set environment variable:
   ```bash
   export CONTEXT7_API_KEY=your-key-here
   ```

### Custom Ranking

In `.context7.yaml`, adjust file priorities:

```yaml
ai_context:
  file_weights:
    ".speckit/constitution/": 10  # Highest priority
    "etl/collector_cian/": 5      # Medium priority
    "tests/": 2                   # Lower priority
```

## Resources

- [Context7 GitHub](https://github.com/upstash/context7)
- [MCP Protocol Docs](https://modelcontextprotocol.io/)
- [Context7 Blog Post](https://upstash.com/blog/context7-mcp)

## Integration with SpecKit

Context7 and SpecKit work together:

1. **SpecKit** defines project structure (constitution, tasks, bugs)
2. **Context7** indexes and injects SpecKit docs into AI prompts
3. **AI Assistant** uses both to understand and modify code

Example workflow:
```
You: "use context7 to implement TASK-001 from current sprint"

Context7: 
  - Injects .speckit/tasks/current-sprint.md
  - Injects .speckit/bugs/incomplete-data.md
  - Injects etl/collector_cian/browser_fetcher.py

AI: "I see TASK-001 is to fix OfferSubtitle parsing. Here's the implementation..."
```

---

**Last updated:** 2025-11-03  
**Questions?** Open an issue on GitHub
