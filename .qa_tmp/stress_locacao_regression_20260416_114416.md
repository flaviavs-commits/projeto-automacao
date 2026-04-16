# Stress Test Locacao - Regressao

- previous_report: .qa_tmp\stress_locacao_20260415_163642.json
- passed_sampled: 10
- failed_repeated: 23
- new_cases: 10
- total_cases: 43
- passed: 11
- failed: 32
- pass_rate: 25.58%

## Por categoria

- audio: 1/11 (9.09%)
- close: 1/1 (100.00%)
- generic: 1/2 (50.00%)
- greeting: 1/1 (100.00%)
- location: 0/11 (0.00%)
- paid_changes: 1/8 (12.50%)
- prices: 1/1 (100.00%)
- risk_materials: 1/1 (100.00%)
- risk_people: 1/4 (25.00%)
- schedule: 1/1 (100.00%)
- structure: 2/2 (100.00%)

## Principais falhas

- location_missing_official_reference: 11
- missing_handoff_text: 10
- audio_missing_negative_constraint: 8
- expected_model=rule_human_handoff got=rule_schedule_site_only: 5
- expected_model=rule_human_handoff got=qwen2.5:0.5b-instruct: 5
- audio_answer_missing_topic: 4
- unexpected_rule_model=rule_schedule_site_only: 1
