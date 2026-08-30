# Evaluation Observations

## Job Details

- **Job name:** support-chatbot-eval-run-3
- **Job ARN:** arn:aws:bedrock:us-east-1:708026873259:evaluation-job/2kl0fuuex06t
- **Status:** Completed
- **Evaluator model:** amazon.nova-pro-v1:0
- **Metric:** Builtin.Correctness

## Results

| Test ID | Category | Score |
|---------|----------|-------|
| t1_bug_report | Bug report (incomplete) | 1.0 |
| t2_bug_report_all_fields | Bug report (complete) | 1.0 |
| t3_faq_shipping | Platform question (covered) | 1.0 |
| t4_faq_returns | Platform question (covered) | 1.0 |
| t5_faq_payments | Platform question (covered) | 1.0 |
| t6_other | Other request | 1.0 |
| t7_ambiguous | Ambiguous (bug + return) | 1.0 |

**Overall score: 1.0 / 1.0 (7/7 tests passed)**

## Observations

- All three routing paths (bug report, platform question, other) produced correct responses.
- The bug-report collection prompt fix resolved the earlier 0.5 score on t1. The model now correctly asks for missing fields instead of filing a ticket prematurely.
- No misrouting observed across the test suite.
- The tool call (`create_bug_report`) succeeded reliably when all three required fields were present.
