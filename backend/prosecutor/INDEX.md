# Prosecutor Agent Documentation Index

Welcome to the Prosecutor Agent documentation. This agent defends the State/Complainant in criminal cases by intelligently querying the lexigraphbe legal retrieval system.

## 📖 Documentation Structure

### For Getting Started
1. **[QUICKSTART.md](./QUICKSTART.md)** - Start here!
   - 5-minute quick start guide
   - Basic usage examples
   - API reference
   - Common patterns
   - Troubleshooting

### For Understanding the System
2. **[ARCHITECTURE.md](./ARCHITECTURE.md)** - System design deep-dive
   - Component interaction diagram
   - Data structures
   - Query flow example
   - Comparison with lexigraphbe standalone
   - Benefits and design rationale
   - Extension points

3. **[FLOW_DIAGRAM.md](./FLOW_DIAGRAM.md)** - Visual flow diagram
   - Complete system flow with ASCII diagrams
   - Phase-by-phase breakdown
   - Cache behavior visualization
   - Query count analysis
   - Efficiency comparison

### For Implementation Details
4. **[README.md](./README.md)** - Comprehensive reference
   - Architecture overview
   - Key features
   - Usage examples
   - Integration with lexigraphbe
   - Data flow
   - Crime analysis structure
   - Real case example
   - Extension points
   - Testing guide
   - Dependencies
   - Performance considerations
   - Future enhancements

### For Testing
5. **[test_prosecutor.py](./test_prosecutor.py)** - Test suite
   - Basic functionality tests
   - Import validation
   - Case analysis verification

6. **[prosecutor.py](./prosecutor.py)** - Main implementation
   - Run with `python prosecutor.py` for a live example

## 🎯 Quick Navigation

### I want to...

- **Get started quickly** → [QUICKSTART.md](./QUICKSTART.md)
- **Understand the architecture** → [ARCHITECTURE.md](./ARCHITECTURE.md)
- **See the complete flow** → [FLOW_DIAGRAM.md](./FLOW_DIAGRAM.md)
- **Read detailed docs** → [README.md](./README.md)
- **Run a test** → `python test_prosecutor.py`
- **See a live example** → `python prosecutor.py`

## 📋 Key Concepts

### What is the Prosecutor Agent?

An AI agent that:
1. Takes a case file as input
2. Uses lexigraphbe to understand legal concepts
3. Identifies crimes and prosecution strategy
4. Queries lexigraphbe **selectively** for specific crimes
5. Supports multi-round trials (opening, rebuttal, closing)

### How is it different from lexigraphbe?

| Aspect | lexigraphbe | Prosecutor Agent |
|--------|-------------|------------------|
| **Input** | Single query | Complete case file |
| **Output** | Legal sections | Prosecutorial arguments |
| **Queries** | One-shot | Multiple, on-demand |
| **Context** | Stateless | Multi-turn memory |
| **Perspective** | Neutral | Prosecutorial |

### Key Innovation: Selective Querying

Instead of running the full lexigraphbe pipeline once, the prosecutor:
1. **Opening**: Queries for primary crime only
2. **Rebuttal**: Queries for additional crimes if defense attacks them
3. **Closing**: Queries for any remaining crimes
4. **Caches** all results to avoid redundant queries

## 🏗️ System Architecture

```
Case File → Stage 1 (Understanding) → Crime Analysis → Selective Queries
                ↓                           ↓               ↓
        LegalQueryObject          ProsecutorAnalysis   LexiGraphAgent
                                                            ↓
                                                    Cached Sections
                                                            ↓
                                        Opening → Rebuttal → Closing
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for detailed diagrams.

## 🚀 Usage Example

```python
from prosecutor import ProsecutorAgent

# Initialize
prosecutor = ProsecutorAgent()

# Analyze case
case = "Woman died at matrimonial home. Dowry demands documented..."
analysis = prosecutor.analyze_case(case)

# Build arguments
opening = prosecutor.build_opening_argument()
# → Queries lexigraphbe for primary crime

rebuttal = prosecutor.handle_rebuttal(defense_argument)
# → May query lexigraphbe if defense attacks new crime

closing = prosecutor.build_closing_argument()
# → Uses cached + queries any remaining crimes
```

See [QUICKSTART.md](./QUICKSTART.md) for more examples.

## 🔗 Integration Points

### With lexigraphbe:
- `query_understanding_agent.py` - Case decomposition
- `query_verifier_agent.py` - Quality assurance
- `stage1_pipeline.py` - Orchestration

### With agents/lexigraph:
- `lexigraph_agent.py` - Full section retrieval

### With LLM:
- Crime analysis and strategy (gpt-4o)
- Counter-argument generation

## 📊 Performance

Typical case with 3 crimes:
- **Opening**: ~15-20 seconds (1 lexigraphbe query)
- **Rebuttal**: ~2-15 seconds (cache hit or new query)
- **Closing**: ~5-30 seconds (query remaining crimes)

Total: ~20-65 seconds (3 lexigraphbe queries)

Compare to: Running full pipeline 3 times (~45-90 seconds)

## 🧪 Testing

```bash
# Quick test
python test_prosecutor.py

# Full example with dowry death case
python prosecutor.py
```

## 📝 Files Overview

| File | Purpose | Lines | Key Content |
|------|---------|-------|-------------|
| `prosecutor.py` | Main implementation | ~500 | ProsecutorAgent class |
| `__init__.py` | Package exports | ~10 | Public API |
| `QUICKSTART.md` | Getting started | ~300 | Usage guide |
| `ARCHITECTURE.md` | System design | ~500 | Design rationale |
| `FLOW_DIAGRAM.md` | Visual flow | ~600 | ASCII diagrams |
| `README.md` | Full documentation | ~400 | Complete reference |
| `test_prosecutor.py` | Test suite | ~50 | Basic tests |

## 🔮 Future Work

- [ ] Parallel crime queries
- [ ] Smart cache invalidation
- [ ] Evidence-to-section mapping
- [ ] Defense agent (mirror architecture)
- [ ] Multi-accused support
- [ ] Real-time transcript analysis

## 🤝 Contributing

To extend the prosecutor agent:

1. **Custom prosecution strategies**: Override `_analyze_prosecution_strategy()`
2. **Enhanced rebuttal logic**: Override `_identify_crime_from_defense()`
3. **Alternative query building**: Override `_build_crime_specific_query()`

See [ARCHITECTURE.md](./ARCHITECTURE.md) § Extension Points for details.

## 📞 Support

For questions about:
- **Prosecutor Agent**: Read this documentation
- **lexigraphbe integration**: See `backend/lexigraphbe/`
- **LexiGraph retrieval**: See `backend/agents/lexigraph/`

## 🎓 Learning Path

1. **Day 1**: Read QUICKSTART.md, run test_prosecutor.py
2. **Day 2**: Read ARCHITECTURE.md, understand design
3. **Day 3**: Read FLOW_DIAGRAM.md, trace execution
4. **Day 4**: Read README.md, explore extensions
5. **Day 5**: Modify prosecutor.py, add custom logic

Happy prosecuting! ⚖️
