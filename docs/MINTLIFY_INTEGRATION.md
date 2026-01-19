# Mintlify Documentation Integration

## Overview

We've integrated **[Mintlify](https://www.mintlify.com)** as our primary documentation platform, providing an AI-native, beautiful, and developer-friendly documentation experience.

## What is Mintlify?

Mintlify is the next generation of documentation platforms, offering:

✨ **AI-Native Features**
- Built-in AI assistant for users
- LLMs.txt and MCP support for AI discoverability
- Self-updating knowledge management
- Context-aware content generation

🎨 **Beautiful by Default**
- Modern UI with dark/light mode
- Mobile-responsive design
- Interactive components
- Zero configuration needed

👨‍💻 **Developer-Friendly**
- MDX-based (Markdown + React components)
- Git-based workflow (changes auto-deploy)
- OpenAPI spec integration
- Mermaid diagram support
- Hot reload in development

## Why Mintlify for n-aible?

1. **Perfect for Technical Projects**
   - Great for FastAPI/Next.js documentation
   - Supports interactive API documentation
   - Mermaid diagrams work seamlessly (all our existing diagrams!)
   - Version control integration

2. **AI Integration**
   - Your docs show up in ChatGPT, Claude, Cursor, Perplexity
   - Users can ask AI questions about your docs
   - MCP support for advanced AI workflows

3. **Low Maintenance**
   - Auto-deploys on git push
   - No build pipeline needed
   - Automatic search indexing
   - SEO optimization built-in

4. **Enterprise-Ready**
   - SOC 2, GDPR, ISO/27001 compliant
   - SAML-based SSO
   - Analytics integration
   - Custom domain support

## Project Structure

```
n-aible_edtech_sims/
├── mintlify-docs/              # Mintlify documentation (git submodule)
│   ├── docs.json               # Configuration
│   ├── index.mdx               # Homepage
│   ├── quickstart.mdx          # Quick start guide
│   ├── quick-reference.mdx     # Quick reference
│   ├── setup/                  # Setup guides
│   ├── architecture/           # Architecture docs
│   ├── features/               # Feature documentation
│   ├── api/                    # API reference
│   ├── development/            # Development guides
│   └── README.md               # Mintlify documentation README
│
├── docs/                       # Original documentation (kept for reference)
│   ├── architecture/
│   ├── Quick_Reference.md
│   └── ...
│
└── MINTLIFY_INTEGRATION.md     # This file
```

## Getting Started with Mintlify

### 1. Local Development

```bash
# Install Mintlify CLI
npm i -g mintlify

# Navigate to mintlify-docs
cd mintlify-docs

# Start local preview
mintlify dev
```

Open [http://localhost:3000](http://localhost:3000) to see your docs!

### 2. Making Changes

1. Edit MDX files in `mintlify-docs/`
2. Changes appear instantly (hot reload)
3. Commit and push to git
4. Mintlify auto-deploys to production

### 3. Adding New Pages

1. Create new `.mdx` file in appropriate directory
2. Add frontmatter:
   ```mdx
   ---
   title: 'Page Title'
   description: 'Page description'
   icon: 'rocket'
   ---
   ```
3. Add to navigation in `docs.json`:
   ```json
   {
     "pages": ["path/to/your-page"]
   }
   ```

## Documentation Organization

### Tabs

Our documentation is organized into 5 main tabs:

1. **Getting Started** - Installation, setup, quick reference
2. **Architecture** - System design, modular structure, diagrams
3. **Features** - Core features, AI integration, workflows
4. **API Reference** - Complete endpoint documentation
5. **Development** - Developer guides, migration, best practices

### Content Types

We use different MDX files for different purposes:

- **Guides** - Step-by-step instructions (`quickstart.mdx`)
- **References** - Quick lookup information (`quick-reference.mdx`)
- **Architecture** - System design and diagrams
- **API Docs** - Endpoint specifications
- **Tutorials** - In-depth learning content

## Migration from Original Docs

We've preserved the original documentation structure in `docs/` while creating Mintlify versions in `mintlify-docs/`. This allows us to:

1. **Keep original docs** for reference and git history
2. **Migrate gradually** to Mintlify format
3. **Maintain both** during transition period
4. **Compare** old vs new documentation

### What's Been Migrated

- ✅ Index page with platform overview
- ✅ Quick start guide with setup instructions
- ✅ Quick reference with common patterns
- ✅ All Mermaid diagrams (PDF pipeline, simulation flow, auth flow)
- ✅ Backend architecture documentation
- ✅ API endpoint structure (ready for content)
- ✅ Development guide structure

### What's Pending

- ⏳ Individual API endpoint documentation
- ⏳ Feature-specific guides
- ⏳ Architecture deep-dives
- ⏳ Migration guides
- ⏳ Best practices guides

## Mintlify Components Used

We leverage Mintlify's rich component library:

### Navigation & Layout
- `<Tabs>` - Tabbed content for code examples
- `<Steps>` - Step-by-step guides
- `<AccordionGroup>` & `<Accordion>` - Collapsible sections

### Content Display
- `<Card>` & `<CardGroup>` - Feature highlights, quick links
- `<CodeGroup>` - Multi-language code blocks
- `<Code>` - Inline code with syntax highlighting

### Callouts
- `<Warning>` - Important warnings
- `<Info>` - Additional information
- `<Check>` - Success messages
- `<Tip>` - Helpful tips

### Interactive
- Mermaid diagrams - Automatic rendering
- OpenAPI integration - Auto-generated API docs
- Search - Built-in instant search
- AI Assistant - Context-aware help

## Deployment

### Development
```bash
cd mintlify-docs
mintlify dev
```
Local preview at http://localhost:3000

### Production
1. **Connect GitHub** in [Mintlify Dashboard](https://dashboard.mintlify.com)
2. **Auto-deployment** - Every push to main triggers build
3. **Preview URLs** - PRs get preview deployments
4. **Custom Domain** - Configure in dashboard

### Manual Deployment
```bash
cd mintlify-docs
mintlify build
mintlify deploy
```

## Configuration

### Main Config (`docs.json`)

```json
{
  "name": "n-aible EdTech Platform",
  "theme": "mint",
  "colors": {
    "primary": "#3B82F6",
    "light": "#60A5FA",
    "dark": "#2563EB"
  },
  "navigation": { ... },
  "contextual": {
    "options": ["copy", "view", "chatgpt", "claude", "mcp", "cursor"]
  }
}
```

### Branding

- Logo: `mintlify-docs/logo/light.svg` and `dark.svg`
- Favicon: `mintlify-docs/favicon.svg`
- Colors: Configured in `docs.json`

### Analytics

Add to `docs.json`:
```json
{
  "analytics": {
    "ga4": {
      "measurementId": "G-XXXXXXXXXX"
    }
  }
}
```

## AI Features

### LLMs.txt

Mintlify automatically generates `llms.txt` at the root of your documentation site. This makes your docs discoverable by:
- ChatGPT (via browsing)
- Claude (via web search)
- Perplexity
- Cursor
- Other AI coding assistants

Users can ask AI questions like:
- "How do I set up n-aible locally?"
- "What's the architecture of n-aible?"
- "Show me how to create a simulation"

And the AI will reference your Mintlify documentation!

### MCP (Model Context Protocol)

Mintlify supports MCP for advanced AI integration:
- Context-aware documentation search
- AI-powered suggestions
- Integration with AI coding assistants

### Built-in AI Assistant

Users get an AI assistant within your docs that:
- Understands your documentation context
- Answers questions about your platform
- Suggests relevant pages
- Helps users find what they need

## OpenAPI Integration

Export your FastAPI OpenAPI spec:

```python
# backend/export_openapi.py
import json
from app.main import app

with open('mintlify-docs/api-reference/openapi.json', 'w') as f:
    json.dump(app.openapi(), f, indent=2)
```

Run when API changes:
```bash
cd backend
python export_openapi.py
```

Mintlify will auto-generate beautiful API docs from the spec!

## Best Practices

1. **Keep docs in sync with code** - Update docs with every feature
2. **Use Mermaid diagrams** - Visual > text for architecture
3. **Include code examples** - Show, don't just tell
4. **Write for humans AND AI** - Docs serve both audiences
5. **Test locally** - Always preview with `mintlify dev`
6. **Use callouts wisely** - Warnings, tips, info appropriately
7. **Link liberally** - Connect related documentation
8. **Update navigation** - Keep `docs.json` organized

## Troubleshooting

### Dev server won't start
```bash
npm i -g mintlify@latest
mintlify dev --clear-cache
```

### Page not showing in navigation
1. Check file path in `docs.json`
2. Verify `.mdx` extension
3. Check frontmatter is valid YAML

### Mermaid diagrams not rendering
- Ensure no syntax errors
- Use triple backticks with `mermaid` language tag
- Test on [mermaid.live](https://mermaid.live/)

### Build fails
```bash
mintlify check  # Check for broken links
cat docs.json | json_pp  # Validate JSON
```

## Resources

- **Mintlify Docs**: https://mintlify.com/docs
- **Mintlify Dashboard**: https://dashboard.mintlify.com
- **Mintlify Community**: https://mintlify.com/community
- **Our Mintlify Docs**: `mintlify-docs/README.md`
- **MDX Documentation**: https://mdxjs.com/
- **Mermaid Guide**: https://mermaid.js.org/

## Migration Checklist

- [x] Set up git submodule
- [x] Configure `docs.json`
- [x] Create homepage (`index.mdx`)
- [x] Create quickstart guide
- [x] Create quick reference with diagrams
- [x] Set up directory structure
- [ ] Migrate individual API endpoints
- [ ] Create feature guides
- [ ] Write architecture deep-dives
- [ ] Add development tutorials
- [ ] Export OpenAPI spec
- [ ] Connect to Mintlify Dashboard
- [ ] Configure custom domain
- [ ] Set up analytics
- [ ] Enable AI assistant

## Support

- **Mintlify Support**: hi@mintlify.com
- **Mintlify Slack**: [Join community](https://mintlify.com/community)
- **GitHub Issues**: For n-aible specific docs issues
- **Documentation**: `mintlify-docs/README.md`

---

**Ready to build amazing AI-native documentation?** 

Head to `mintlify-docs/` and run `mintlify dev` to get started! 🚀

