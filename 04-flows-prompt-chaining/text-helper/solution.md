# Exercise Solution – Text Helper Flow

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

Each branch ends in its own Flow output node — a Flow output node accepts exactly one
incoming connection, so a single shared output node fails at **Prepare**.

---

## Node 1: DecideOperation

**Prompt template:**
```
You are an operation classifier for a text editing tool. Your only job is to read the user's message and decide which operation they want: summarize, rewrite, or other.

Output exactly one word: "summarize", "rewrite", or "other". No explanation, no punctuation, no extra text.

Use "summarize" for requests about condensing, shortening, giving the main points, or producing a summary.
Use "rewrite" for requests about improving clarity, readability, simplifying language, or rephrasing.
Use "other" if the message does not appear to be a text processing request at all.

User message:
<message>
{{user_message}}
</message>

Which operation should be applied: summarize, rewrite, or other?
```

**Input variable:** `user_message` (String)

---

## Condition Node: RouteByOperation

- **Condition 1:** `operation == "summarize"` → Summarizer
- **Condition 2:** `operation == "rewrite"` → Rewriter
- **Default (else):** → OtherResponder

Wire: `DecideOperation` model output → condition input `operation`

The else branch catches both explicit `"other"` outputs and any unexpected classifier output.

---

## Node 2A: Summarizer

**Prompt template:**
```
You are a precise summarization assistant. The user's message contains their request followed by the text they want summarized. Extract the text and produce two things:

1. A 5-bullet summary — each bullet captures one distinct main point from the text. Keep each bullet under 20 words.
2. A TL;DR — one sentence (under 25 words) that captures the single most important takeaway.

Format your output exactly like this:
**Summary:**
- [bullet 1]
- [bullet 2]
- [bullet 3]
- [bullet 4]
- [bullet 5]

**TL;DR:** [one sentence]

Do not add bullets about topics not present in the text. Do not editorialize.

User message:
<message>
{{user_message}}
</message>
```

**Input variable:** `user_message` (String)

---

## Node 2B: Rewriter

**Prompt template:**
```
You are a clarity editor. The user's message contains their request followed by the text they want rewritten. Extract the text and rewrite it to be easier to read while preserving the original meaning exactly.

Rules:
- Do not add information that is not in the original
- Do not remove any meaningful content
- Use shorter sentences where possible
- Replace jargon or overly complex phrasing with plain language
- Keep the same general structure and paragraph breaks as the original
- Do not add a preamble — output the rewritten text directly

User message:
<message>
{{user_message}}
</message>
```

**Input variable:** `user_message` (String)

---

## Node 2C: OtherResponder

**Prompt template:**
```
You are a text editing assistant. The user's message does not clearly request a summarize or rewrite operation.

Write a brief, polite response that:
- Acknowledges the message
- Does not attempt to process any text
- Ask the user to rewrite the question, to clearly state if the want to summarize or rewrite the text

Keep the response under 60 words.

User message:
<message>
{{user_message}}
</message>
```

**Input variable:** `user_message` (String)

---

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

---

## Why These Prompts Work

**DecideOperation:** The classifier prompt is strict about output format ("exactly one word") and defines explicit behavior for all three cases — including inputs that aren't text processing requests. Adding `"other"` as an explicit output is better than relying on a default: it gives the model a named category for edge cases rather than forcing everything into `"rewrite"`.

**OtherResponder:** The prompt instructs the node not to process any text and to ask for clarification instead. This mirrors the pattern from the classifier: when the intent is unclear, the response should be to ask, not to guess.

**Summarizer and Rewriter:** Both nodes receive the full `user_message` and are instructed to extract the text themselves. This keeps the flow simple — one input variable flows through every node, and no node needs to split or transform the input before passing it downstream.
