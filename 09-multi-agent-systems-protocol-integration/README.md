# Multi-Agent Systems Protocol Integration

## Projects in This Directory

### 1. content-moderation-pipeline ✅ COMPLETE
- **Status:** Fully implemented and tested
- **Tests:** 24/24 unit tests passing
- **Live AWS:** Nova Lite + Nova Pro working
- **README:** Updated with test results

### 2. healthcare-triage-demo ✅ DATA VALIDATED
- **Status:** Implementation complete, data validated
- **Patients:** 3 (P-1001 emergency, P-1002 mild, P-1003 moderate)
- **Symptom Conditions:** 6 with severity levels
- **To Test:** Use `MODEL_ID=amazon.nova-lite-v1:0` to avoid Claude access issues

### 3. incident-response-demo 🔄 READY TO TEST
- **Status:** Scaffold complete, ready for testing
- **Pipeline:** Alert Router → Root Cause Analyzer → Status Drafter
- **Models:** Nova Lite, Claude Sonnet, Nova Pro
- **To Test:** Use Nova Lite for all models to avoid Claude access issues

### 4. smart-home-device-mgmt ✅ DATA VALIDATED
- **Status:** Implementation complete, data validated
- **Devices:** 3 (thermostat, smart_lock, camera)
- **Diagnostic Rules:** 3 (overheating, firmware_issue, low_battery)
- **To Test:** Use `MODEL_ID=amazon.nova-lite-v1:0` to avoid Claude access issues

## Testing Notes

### Claude Sonnet Access
Claude Sonnet (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) requires AWS Marketplace subscription.
- ❌ Not available with current credentials
- ✅ Workaround: Use `amazon.nova-lite-v1:0` for all models

### Credentials Used
```
AWS_ACCESS_KEY_ID: ASIAQ7KMSUUSXEV3FMGW
AWS_SECRET_ACCESS_KEY: cPzCMQYra9BXHbfGfnVmrd8YET+YUnpLYyHTakG6
AWS_SESSION_TOKEN: IQoJb3JpZ2luX2VjEJX//////////wEaCXVzLXdlc3QtMiJIMEYCIQ...
AWS_REGION: us-east-1
```

### Quick Commands

```bash
# Content Moderation
cd content-moderation-pipeline
uv run python -m pytest test/test_main.py -v  # 24 tests
uv run python demo.py                           # Demo

# Healthcare Triage (with Nova Lite)
cd healthcare-triage-demo
echo "MODEL_ID=amazon.nova-lite-v1:0" >> .env
uv run python main.py --patient-id P-1001

# Incident Response (with Nova Lite)
cd incident-response-demo
echo "NOVA_LITE_MODEL=amazon.nova-lite-v1:0" >> .env
echo "CLAUDE_MODEL=amazon.nova-lite-v1:0" >> .env
echo "NOVA_PRO_MODEL=amazon.nova-lite-v1:0" >> .env
uv run python main.py --incident-id INC-001

# Smart Home (with Nova Lite)
cd smart-home-device-mgmt
echo "MODEL_ID=amazon.nova-lite-v1:0" >> .env
uv run python main.py --device-id DEV-001
```
