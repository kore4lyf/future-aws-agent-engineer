# Exercise: Text Helper Flow

Build a Bedrock Flow that processes text editing requests using conditional routing.

## Flow Structure

```
Flow Input (user_message)
    │
    ▼
[DecideOperation]  →  "summarize", "rewrite", or "other"
    │
    ▼
[RouteByOperation]
    ├── operation == "summarize"  →  [Summarizer]      →  SummarizerOutput
    ├── operation == "rewrite"    →  [Rewriter]        →  RewriterOutput
    └── else                      →  [OtherResponder]  →  OtherOutput
```

## What You Need to Build

### Node 1: DecideOperation (Prompt Node)

Create a prompt node that classifies the user's request into one of three operations:
- **summarize**: condensing, shortening, main points
- **rewrite**: improving clarity, readability, simplifying
- **other**: not a text processing request

**Requirements:**
- Input variable: `user_message` (String)
- Output: exactly one word ("summarize", "rewrite", or "other")
- No explanation, no punctuation, no extra text

### Condition Node: RouteByOperation

Create a condition node that routes based on the classifier output:
- Condition 1: `operation == "summarize"` → Summarizer
- Condition 2: `operation == "rewrite"` → Rewriter
- Default (else): → OtherResponder

### Node 2A: Summarizer (Prompt Node)

Create a prompt node that produces:
1. A 5-bullet summary (each under 20 words)
2. A TL;DR sentence (under 25 words)

**Requirements:**
- Input variable: `user_message` (String)
- Output format: `**Summary:**` followed by bullets, then `**TL;DR:**`

### Node 2B: Rewriter (Prompt Node)

Create a prompt node that rewrites text for clarity while preserving meaning.

**Requirements:**
- Input variable: `user_message` (String)
- No preamble — output rewritten text directly
- Shorter sentences, plain language

### Node 2C: OtherResponder (Prompt Node)

Create a prompt node that politely asks for clarification.

**Requirements:**
- Input variable: `user_message` (String)
- Under 60 words
- Ask user to clarify if they want to summarize or rewrite

## Connection Map

| From | To | Mapping |
|------|----|---------|
| Flow input | DecideOperation | `user_message` → `user_message` |
| DecideOperation (model output) | RouteByOperation | response → `operation` |
| Flow input | Summarizer | `user_message` → `user_message` |
| Flow input | Rewriter | `user_message` → `user_message` |
| Flow input | OtherResponder | `user_message` → `user_message` |
| Summarizer (model output) | SummarizerOutput | response → output |
| Rewriter (model output) | RewriterOutput | response → output |
| OtherResponder (model output) | OtherOutput | response → output |

## Test Inputs

**Test 1 — Summarize:**
```
Please summarize this article:
Artificial intelligence is transforming healthcare. From diagnostic imaging to drug discovery, AI systems are helping doctors make faster, more accurate decisions. However, concerns about data privacy and algorithmic bias remain significant challenges that the industry must address.
```

**Test 2 — Rewrite:**
```
Please rewrite this for clarity:
The implementation of the new system was completed by the team utilizing the recently acquired infrastructure resources which were procured during the previous fiscal quarter.
```

**Test 3 — Other:**
```
What's the weather like today?
```

## Notes

- Each branch ends in its own Flow output node (single input only)
- The condition node's else branch catches unexpected classifier outputs
- All nodes receive the full `user_message` from Flow input

See `solution.md` for the complete prompts and configuration.
