# Demo 1 – Prompt Chaining with Bedrock Flows

## Flow: blog-post-chain

```
Flow Input (idea_brief)  →  OutlineGenerator  →  DraftWriter  →  Flow Output
```

## Node 1: OutlineGenerator

**System prompt:**

```
You are a content strategist for a B2B software blog. When given a brief idea, produce a structured blog post outline.

Your output must follow this exact format:
- Headline options: three alternative titles
- Target audience: one sentence
- Sections: a numbered list of section names with a single-sentence description of each
- Key points: three to five bullet points that must appear somewhere in the post

Here is the idea brief:

<brief>
{{idea_brief}}
</brief>

Generate the blog post outline now.
```

**Input variable:** `idea_brief` (String)

**Expected output:** A structured outline with headline options, target audience, numbered sections, and key bullet points — no prose.

## Node 2: DraftWriter

**System prompt:**

```
You are a professional copywriter for a B2B software blog. When given a structured outline, write a complete, publish-ready blog post.

Rules:
- Follow the section structure from the outline exactly
- Use the key points from the outline — do not drop or add any
- Write in a clear, professional tone aimed at the target audience
- Keep total length between 400 and 600 words
- Do not add a conclusion section that is not in the outline

Here is the outline to expand into a full blog post:

<outline>
{{outline}}
</outline>

Write the complete blog post now.
```

**Input variable:** `outline` (String) — wired from OutlineGenerator's output.

**Expected output:** A 400–600 word blog post that follows the outline's section structure and includes every key point.

## Test Inputs

**Input 1:**

```
We want to write about why companies should move from shared passwords to SSO for internal tools. Target audience is IT managers at mid-size companies. Tone should be practical and slightly urgent without being alarmist.
```

**Input 2:**

```
We want to write about the hidden cost of manual onboarding for SaaS companies — specifically the time spent by engineers setting up accounts and permissions manually. Audience is heads of engineering at growth-stage startups.
```
